# -*- coding: utf-8 -*-
"""
المرحلة 8: وحدة مزامنة الضرائب
modules/taxes_sync.py

الغرض:
- مزامنة سجلات الضرائب (account.tax) من المصدر إلى الوجهة.
- هذه الوحدة ضرورية لضمان مزامنة الضرائب بشكل صحيح قبل الفواتير.
"""

import logging

class TaxSyncModule:
    """
    وحدة متخصصة لمزامنة سجلات الضرائب (account.tax).
    """
    MODEL = 'account.tax'
    # الحقول الأساسية للضريبة. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'amount', 'type_tax_use', 'company_id', 'active'
    ]

    def __init__(self, source_conn, dest_conn, key_manager, last_sync_time, loggers=None):
        """
        تهيئة الوحدة بالخدمات التي تحتاجها من المحرك.

        Args:
            source_conn: كائن اتصال Odoo API للمصدر.
            dest_conn: كائن اتصال Odoo API للوجهة.
            key_manager: كائن مدير مفاتيح المزامنة.
            last_sync_time: آخر طابع زمني للمزامنة الناجحة.
            loggers (dict): قاموس يحتوي على كائنات المنسق (loggers) المختلفة.
        """
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        self.last_sync_time = last_sync_time
        # إضافة حقل المزامنة المخصص إلى قائمة الحقول المطلوبة في الوجهة.
        # هذا الحقل يستخدم لربط السجلات بين المصدر والوجهة.
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_tax_sync_id']

        self.logger = loggers.get("taxes_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة الضرائب.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة الضرائب...")
        
        # 1. جلب جميع الشركات من المصدر.
        source_companies = self.source['res.company'].search_read([], ['id', 'name'])
        
        if not source_companies:
            print("  - لا توجد شركات في المصدر لمزامنة الضرائب.")
            return

        total_companies = len(source_companies)
        for i, company in enumerate(source_companies):
            print(f"\n--- مزامنة الضرائب للشركة: {company.get('name')} (ID: {company['id']}) ({i+1}/{total_companies}) ---")
            
            # جلب معرف الشركة المقابل في الوجهة باستخدام `x_company_sync_id`.
            dest_company_ids_in_dest = self.dest['res.company'].search([('x_company_sync_id', '=', str(company['id']))], limit=1)
            if not dest_company_ids_in_dest:
                print(f"  - تحذير: لم يتم العثور على الشركة ID {company['id']} في الوجهة عبر x_company_sync_id. سيتم تخطي ضرائب هذه الشركة.")
                continue
            dest_company_id = dest_company_ids_in_dest[0]

            # البحث عن الضرائب الخاصة بهذه الشركة في المصدر.
            # استخدام `write_date` للمزامنة التزايدية.
            company_taxes_ids = self.source['account.tax'].search([
                ('company_id', '=', company['id']),
                ('write_date', '>', self.last_sync_time)
            ])
            company_taxes_data = self.source['account.tax'].read(company_taxes_ids, self.FIELDS_TO_SYNC)
            
            total_taxes_in_company = len(company_taxes_data)
            print(f"  - تم العثور على {total_taxes_in_company} ضريبة في المصدر لهذه الشركة.")

            # 2. تجهيز السجلات للمزامنة الدفعية.
            records_to_create = []
            records_to_update = []

            for j, tax_record in enumerate(company_taxes_data):
                self.logger.debug(f"    - معالجة ضريبة {j+1}/{total_taxes_in_company}: {tax_record.get('name')} (ID: {tax_record['id']})")
                source_id = tax_record['id']
                source_name = tax_record.get('name')
                source_type_tax_use = tax_record.get('type_tax_use')

                transformed_data = self._transform_data(tax_record, dest_company_id)

                # 1. البحث في الوجهة مباشرة باستخدام `x_tax_sync_id`.
                search_domain_x_sync_id = [('x_tax_sync_id', '=', str(source_id))]
                existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

                if existing_record_by_x_sync_id:
                    destination_id = existing_record_by_x_sync_id[0]
                    records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
                else:
                    # 2. إذا لم يتم العثور عليه عبر `x_tax_sync_id`، حاول البحث بالاسم والنوع والشركة.
                    search_domain_by_name = [
                        ('name', '=', source_name),
                        ('type_tax_use', '=', source_type_tax_use),
                        ('company_id', '=', dest_company_id)
                    ]
                    existing_record_by_name = self.dest[self.MODEL].search(search_domain_by_name, limit=1)

                    if existing_record_by_name:
                        destination_id = existing_record_by_name[0]
                        transformed_data['x_tax_sync_id'] = str(source_id)
                        records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
                    else:
                        # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                        transformed_data['x_tax_sync_id'] = str(source_id)
                        records_to_create.append({'data': transformed_data, 'source_id': source_id})
            
            self._batch_sync_records(records_to_create, records_to_update)
            
        self.logger.info("اكتملت مزامنة الضرائب.")

    def _batch_sync_records(self, records_to_create, records_to_update):
        """
        يقوم بمزامنة السجلات على دفعات (batch) لزيادة الكفاءة.
        """
        self.logger.info(f"بدء المزامنة الدفعية: {len(records_to_create)} سجلات للإنشاء، {len(records_to_update)} سجلات للتحديث.")

        # إنشاء السجلات الجديدة
        if records_to_create:
            self.logger.info(f"إنشاء {len(records_to_create)} سجل جديد...")
            try:
                new_records_data = [rec['data'] for rec in records_to_create]
                new_destination_ids = self.dest[self.MODEL].create(new_records_data)
                for i, new_destination_id in enumerate(new_destination_ids):
                    source_id = records_to_create[i]['source_id']
                    self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                    self.activity_logger.info(f"    - تم إنشاء ضريبة جديدة في الوجهة بمعرف ID: {new_destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات الضرائب الجديدة دفعيًا. الخطأ: {e}")

        # تحديث السجلات الموجودة
        if records_to_update:
            self.logger.info(f"تحديث {len(records_to_update)} سجل موجود...")
            try:
                for record_data in records_to_update:
                    destination_id = record_data['id']
                    source_id = record_data['source_id']
                    data = record_data['data']
                    self.dest[self.MODEL].write([destination_id], data)
                    self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                    self.activity_logger.info(f"    - تم تحديث ضريبة موجودة في الوجهة ID: {destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات الضرائب دفعيًا. الخطأ: {e}")

        self.logger.info("اكتملت المزامنة الدفعية للضرائب.")

        self._handle_deletions()

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف الضرائب...")
        
        # 1. جلب جميع معرفات المصدر المخزنة محليًا لـ account.tax.
        mapped_source_ids = self.key_manager.get_all_source_ids_for_model(self.MODEL)
        self.logger.debug(f"  - تم العثور على {len(mapped_source_ids)} معرف مصدر mapped لـ {self.MODEL}.")

        if not mapped_source_ids:
            self.logger.info("  - لا توجد معرفات مصدر mapped لـ account.tax. تخطي معالجة الحذف.")
            return

        # 2. جلب جميع معرفات account.tax النشطة من نظام المصدر.
        active_source_ids = self.source[self.MODEL].search([])
        self.logger.debug(f"  - تم العثور على {len(active_source_ids)} معرف account.tax نشط في المصدر.")

        # 3. تحديد السجلات التي تم حذفها في المصدر (موجودة في mapped_source_ids ولكن ليست في active_source_ids).
        deleted_source_ids = [sid for sid in mapped_source_ids if sid not in active_source_ids]
        self.logger.info(f"  - تم تحديد {len(deleted_source_ids)} سجل account.tax للحذف (الأرشفة) في الوجهة.")

        if not deleted_source_ids:
            self.logger.info("  - لا توجد سجلات محذوفة في المصدر تتطلب الأرشفة في الوجهة.")
            return

        # 4. أرشفة السجلات المحذوفة في الوجهة وإزالة الربط.
        for source_id in deleted_source_ids:
            destination_id = self.key_manager.get_destination_id(self.MODEL, source_id)
            if destination_id:
                try:
                    # أرشفة السجل في الوجهة (ضبط active = False).
                    self.dest[self.MODEL].write([destination_id], {'active': False})
                    self.key_manager.remove_mapping(self.MODEL, source_id)
                    self.activity_logger.info(f"    - تم أرشفة الضريبة ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة الضريبة ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ account.tax المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف الضرائب.")

    def _sync_record(self, source_record, dest_company_id):
        """
        هذه الدالة لم تعد تستخدم بشكل مباشر للمزامنة الفردية بعد التحول للمزامنة الدفعية.
        يمكن إزالتها أو تعديلها لتناسب أي استخدامات مستقبلية.
        """
        self.logger.warning("الدالة _sync_record تم استدعاؤها ولكنها لم تعد تستخدم للمزامنة الفردية. يرجى التحقق.")
        pass

    

    def _transform_data(self, source_record, dest_company_id):
        """
        تحويل بيانات الضريبة من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)
        data_to_sync['company_id'] = dest_company_id
        return data_to_sync
