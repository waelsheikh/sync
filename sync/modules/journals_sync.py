# -*- coding: utf-8 -*-
"""
المرحلة 8: وحدة مزامنة دفاتر اليومية
modules/journals_sync.py

الغرض:
- مزامنة دفاتر اليومية (account.journal) من المصدر إلى الوجهة.
- تعتمد هذه الوحدة على وجود شجرة الحسابات في الوجهة.
"""

import logging

class JournalSyncModule:
    """
    وحدة متخصصة لمزامنة دفاتر اليومية (account.journal).
    """
    MODEL = 'account.journal'
    # الحقول الأساسية لدفتر اليومية. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'code', 'type', 'default_account_id', 'company_id'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_journal_sync_id']

        self.logger = loggers.get("journals_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة دفاتر اليومية.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        self.logger.info("بدء مزامنة دفاتر اليومية...")
        
        # 1. استخراج البيانات من المصدر.
        # جلب فقط السجلات التي تم تعديلها منذ آخر مزامنة (باستخدام write_date).
        source_ids = self.source[self.MODEL].search([('write_date', '>', self.last_sync_time)])
        source_data = self.source[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        self.logger.info(f"تم العثور على {total_records} دفتر يومية في المصدر.")

        # 2. تجهيز السجلات للمزامنة الدفعية.
        records_to_create = []
        records_to_update = []

        for i, record in enumerate(source_data):
            self.logger.debug(f"  - معالجة دفتر {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            source_id = record['id']
            code = record.get('code')

            transformed_data = self._transform_data(record)
            if not transformed_data:
                continue # توقف إذا فشل التحويل (مثلاً لم يتم العثور على حساب أساسي).

            # 1. البحث في الوجهة مباشرة باستخدام `x_journal_sync_id`.
            search_domain_x_sync_id = [('x_journal_sync_id', '=', str(source_id))]
            existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

            if existing_record_by_x_sync_id:
                destination_id = existing_record_by_x_sync_id[0]
                update_data = transformed_data.copy()
                update_data.pop('type', None) # حقل 'type' ليس قابلاً للتحديث بعد الإنشاء.
                records_to_update.append({'id': destination_id, 'data': update_data, 'source_id': source_id})
            else:
                # 2. إذا لم يتم العثور عليه عبر `x_journal_sync_id`، حاول البحث بالكود ومعرف الشركة.
                search_domain_by_code = [
                    ('code', '=', code),
                    ('type', '=', record.get('type')),
                    ('company_id', '=', transformed_data['company_id'])
                ]
                existing_record_by_code = self.dest[self.MODEL].search(search_domain_by_code, limit=1)

                if existing_record_by_code:
                    destination_id = existing_record_by_code[0]
                    update_data = transformed_data.copy()
                    update_data.pop('type', None) # حقل 'type' ليس قابلاً للتحديث بعد الإنشاء.
                    update_data['x_journal_sync_id'] = str(source_id)
                    records_to_update.append({'id': destination_id, 'data': update_data, 'source_id': source_id})
                else:
                    # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                    transformed_data['x_journal_sync_id'] = str(source_id)
                    records_to_create.append({'data': transformed_data, 'source_id': source_id})

        self._batch_sync_records(records_to_create, records_to_update)
            
        self.logger.info("اكتملت مزامنة دفاتر اليومية.")

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
                    self.activity_logger.info(f"    - تم إنشاء دفتر يومية جديد في الوجهة بمعرف ID: {new_destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات دفاتر اليومية الجديدة دفعيًا. الخطأ: {e}")

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
                    self.activity_logger.info(f"    - تم تحديث دفتر يومية موجود في الوجهة ID: {destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات دفاتر اليومية دفعيًا. الخطأ: {e}")

        self.logger.info("اكتملت المزامنة الدفعية لدفاتر اليومية.")

        self._handle_deletions()

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف دفاتر اليومية...")
        
        # 1. جلب جميع معرفات المصدر المخزنة محليًا لـ account.journal.
        mapped_source_ids = self.key_manager.get_all_source_ids_for_model(self.MODEL)
        self.logger.debug(f"  - تم العثور على {len(mapped_source_ids)} معرف مصدر mapped لـ {self.MODEL}.")

        if not mapped_source_ids:
            self.logger.info("  - لا توجد معرفات مصدر mapped لـ account.journal. تخطي معالجة الحذف.")
            return

        # 2. جلب جميع معرفات account.journal النشطة من نظام المصدر.
        active_source_ids = self.source[self.MODEL].search([])
        self.logger.debug(f"  - تم العثور على {len(active_source_ids)} معرف account.journal نشط في المصدر.")

        # 3. تحديد السجلات التي تم حذفها في المصدر (موجودة في mapped_source_ids ولكن ليست في active_source_ids).
        deleted_source_ids = [sid for sid in mapped_source_ids if sid not in active_source_ids]
        self.logger.info(f"  - تم تحديد {len(deleted_source_ids)} سجل account.journal للحذف (الأرشفة) في الوجهة.")

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
                    self.activity_logger.info(f"    - تم أرشفة دفتر اليومية ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة دفتر اليومية ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ account.journal المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف دفاتر اليومية.")

    def _sync_record(self, source_record):
        """
        هذه الدالة لم تعد تستخدم بشكل مباشر للمزامنة الفردية بعد التحول للمزامنة الدفعية.
        يمكن إزالتها أو تعديلها لتناسب أي استخدامات مستقبلية.
        """
        self.logger.warning("الدالة _sync_record تم استدعاؤها ولكنها لم تعد تستخدم للمزامنة الفردية. يرجى التحقق.")
        pass

    

    def _transform_data(self, source_record):
        """
        تحويل بيانات دفتر اليومية من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.
        يتضمن معالجة العلاقات (مثل company_id, default_account_id).

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # التأكد من وجود حقل 'type' دائمًا في البيانات.
        if 'type' in source_record:
            data_to_sync['type'] = source_record['type']
        else:
            self.logger.warning(f"    - تحذير: حقل 'type' مفقود من سجل المصدر لدفتر اليومية '{source_record.get('name')}'.")

        # جلب معرف الشركة المقابل في الوجهة باستخدام `x_company_sync_id`.
        final_dest_company_id = 1 # القيمة الافتراضية لمعرف الشركة (عادةً الشركة الرئيسية).
        if data_to_sync.get('company_id'):
            source_company_id = data_to_sync['company_id'][0]
            dest_company_ids_in_dest = self.dest['res.company'].search([('x_company_sync_id', '=', str(source_company_id))], limit=1)
            if dest_company_ids_in_dest:
                final_dest_company_id = dest_company_ids_in_dest[0]
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على الشركة ID {source_company_id} في الوجهة عبر x_company_sync_id. سيتم استخدام الشركة الافتراضية (ID 1).")
        data_to_sync['company_id'] = final_dest_company_id # تعيين معرف الشركة المحدد.

        # ربط الحساب الافتراضي (default_account_id).
        if data_to_sync.get('default_account_id'):
            source_account_id = data_to_sync['default_account_id'][0] if isinstance(data_to_sync['default_account_id'], list) else data_to_sync['default_account_id']
            # جلب معرف الحساب المقابل في الوجهة باستخدام `x_account_sync_id`.
            dest_account_ids_in_dest = self.dest['account.account'].search([('x_account_sync_id', '=', str(source_account_id))], limit=1)
            
            if dest_account_ids_in_dest:
                dest_account_id = dest_account_ids_in_dest[0]
                # جلب معرفات الشركات المرتبطة بالحساب في الوجهة.
                account_info = self.dest['account.account'].read([dest_account_id], ['company_ids'])[0]
                account_company_ids = account_info.get('company_ids', [])

                # التحقق مما إذا كانت شركة دفتر اليومية موجودة ضمن شركات الحساب.
                if final_dest_company_id in account_company_ids:
                    data_to_sync['default_account_id'] = dest_account_id
                else:
                    self.error_logger.error(f"    - خطأ فادح: الحساب الافتراضي ID {source_account_id} لدفتر اليومية '{data_to_sync['name']}' ينتمي لشركة مختلفة في الوجهة. لا يمكن مزامنة هذا الدفتر.")
                    return None
            else:
                self.error_logger.error(f"    - خطأ فادح: الحساب الافتراضي ID {source_account_id} لدفتر اليومية '{data_to_sync['name']}' غير موجود في الوجهة. لا يمكن مزامنة هذا الدفتر.")
                return None

        return data_to_sync