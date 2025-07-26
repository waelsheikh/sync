# -*- coding: utf-8 -*-
"""
المرحلة 6: وحدة مزامنة الشركات
modules/company_sync.py

الغرض:
- مزامنة بيانات الشركات (res.company) من نظام المصدر إلى نظام الوجهة.
- هذه الوحدة حاسمة لأن العديد من السجلات الأخرى (مثل الحسابات ودفاتر اليومية) تعتمد على company_id.
"""

import logging

class CompanySyncModule:
    """
    وحدة متخصصة لمزامنة الشركات (res.company).
    """
    MODEL = 'res.company'
    # قائمة الحقول التي نريد مزامنتها. يمكن تعديلها حسب الحاجة.
    FIELDS_TO_SYNC = [
        'id', 'name', 'currency_id', 'phone', 'email', 'website', 'vat', 'company_registry'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_company_sync_id']

        self.logger = loggers.get("company_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة الشركات.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        self.logger.info("بدء مزامنة الشركات...")
        
        # 1. استخراج البيانات من المصدر.
        # بالنسبة للشركات، نقوم دائمًا بجلب جميع السجلات لضمان وجودها في ذاكرة الربط.
        source_ids = self.source[self.MODEL].search([])
        source_data = self.source[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        self.logger.info(f"تم العثور على {total_records} شركة في المصدر.")

        # 2. تجهيز السجلات للمزامنة الدفعية.
        records_to_create = []
        records_to_update = []
        
        for i, record in enumerate(source_data):
            self.logger.debug(f"  - معالجة شركة {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            source_id = record['id']
            company_name = record.get('name')
            transformed_data = self._transform_data(record)

            # 1. البحث في الوجهة مباشرة باستخدام حقل `x_company_sync_id`.
            search_domain_x_sync_id = [('x_company_sync_id', '=', str(source_id))]
            existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

            if existing_record_by_x_sync_id:
                destination_id = existing_record_by_x_sync_id[0]
                records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
            else:
                # 2. إذا لم يتم العثور عليه عبر x_company_sync_id، حاول البحث بالاسم في Odoo الوجهة.
                existing_dest_company_ids_by_name = self.dest[self.MODEL].search([('name', '=', company_name)], limit=1)
                if existing_dest_company_ids_by_name:
                    destination_id = existing_dest_company_ids_by_name[0]
                    # Update x_company_sync_id for existing records found by name
                    transformed_data['x_company_sync_id'] = str(source_id)
                    records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
                else:
                    # 3. إذا لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء شركة جديدة.
                    transformed_data['x_company_sync_id'] = str(source_id)
                    records_to_create.append({'data': transformed_data, 'source_id': source_id})

        self._batch_sync_records(records_to_create, records_to_update)
        
        self.logger.info("اكتملت مزامنة الشركات.")

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
                    self.activity_logger.info(f"    - تم إنشاء شركة جديدة في الوجهة بمعرف ID: {new_destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات الشركات الجديدة دفعيًا. الخطأ: {e}")

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
                    self.activity_logger.info(f"    - تم تحديث شركة موجودة في الوجهة ID: {destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات الشركات دفعيًا. الخطأ: {e}")

        self.logger.info("اكتملت المزامنة الدفعية للشركات.")

        self._handle_deletions()

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف الشركات...")
        
        # 1. جلب جميع معرفات المصدر المخزنة محليًا لـ res.company.
        mapped_source_ids = self.key_manager.get_all_source_ids_for_model(self.MODEL)
        self.logger.debug(f"  - تم العثور على {len(mapped_source_ids)} معرف مصدر mapped لـ {self.MODEL}.")

        if not mapped_source_ids:
            self.logger.info("  - لا توجد معرفات مصدر mapped لـ res.company. تخطي معالجة الحذف.")
            return

        # 2. جلب جميع معرفات res.company النشطة من نظام المصدر.
        active_source_ids = self.source[self.MODEL].search([])
        self.logger.debug(f"  - تم العثور على {len(active_source_ids)} معرف res.company نشط في المصدر.")

        # 3. تحديد السجلات التي تم حذفها في المصدر (موجودة في mapped_source_ids ولكن ليست في active_source_ids).
        deleted_source_ids = [sid for sid in mapped_source_ids if sid not in active_source_ids]
        self.logger.info(f"  - تم تحديد {len(deleted_source_ids)} سجل res.company للحذف (الأرشفة) في الوجهة.")

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
                    self.activity_logger.info(f"    - تم أرشفة الشركة ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة الشركة ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ res.company المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف الشركات.")

    

    

    def _transform_data(self, source_record):
        """
        تحويل بيانات الشركة من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # معالجة currency_id (ربط العملة).
        # نفترض أن معرفات العملات متناسقة أو يمكن ربطها مباشرة.
        # في سيناريو أكثر تعقيدًا، قد تحتاج إلى وحدة مزامنة للعملات.
        if data_to_sync.get('currency_id'):
            source_currency_id = data_to_sync['currency_id'][0]
            data_to_sync['currency_id'] = source_currency_id
            
        return data_to_sync