# -*- coding: utf-8 -*-
"""
المرحلة 7: وحدة مزامنة شجرة الحسابات
modules/accounts_sync.py

الغرض:
- مزامنة شجرة الحسابات (account.account) من المصدر إلى الوجهة.
- هذه الوحدة بسيطة نسبيًا لأن الحسابات لا تحتوي على علاقات معقدة كثيرة.
"""

import logging

class AccountSyncModule:
    """
    وحدة متخصصة لمزامنة شجرة الحسابات (account.account).
    """
    MODEL = 'account.account'
    # الحقول الأساسية للحساب. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'code', 'reconcile', 'company_ids', 'account_type', 'write_date'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_account_sync_id']

        self.logger = loggers.get("accounts_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة شجرة الحسابات.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        self.logger.info("بدء مزامنة شجرة الحسابات...")
        
        # 1. جلب جميع الشركات من المصدر.
        source_companies = self.source['res.company'].search_read([], ['id', 'name'])
        
        if not source_companies:
            self.logger.info("  - لا توجد شركات في المصدر لمزامنة الحسابات.")
            return

        total_companies = len(source_companies)
        for i, company in enumerate(source_companies):
            self.logger.info(f"\n--- مزامنة الحسابات للشركة: {company.get('name')} (ID: {company['id']}) ({i+1}/{total_companies}) ---")
            
            # جلب معرف الشركة المقابل في الوجهة باستخدام `x_company_sync_id`.
            dest_company_ids_in_dest = self.dest['res.company'].search([('x_company_sync_id', '=', str(company['id']))], limit=1)
            if not dest_company_ids_in_dest:
                self.logger.warning(f"  - تحذير: لم يتم العثور على الشركة ID {company['id']} في الوجهة عبر x_company_sync_id. سيتم تخطي حسابات هذه الشركة.")
                continue
            dest_company_id = dest_company_ids_in_dest[0]

            # البحث عن الحسابات الخاصة بهذه الشركة في المصدر.
            # استخدام `write_date` للمزامنة التزايدية.
            company_accounts_ids = self.source['account.account'].search([
                ('company_ids', 'in', [company['id']]),
                ('write_date', '>', self.last_sync_time)
            ])
            company_accounts_data = self.source['account.account'].read(company_accounts_ids, self.FIELDS_TO_SYNC)
            
            total_accounts_in_company = len(company_accounts_data)
            self.logger.info(f"  - تم العثور على {total_accounts_in_company} حساب في المصدر لهذه الشركة.")

            # 2. تجهيز السجلات للمزامنة الدفعية.
            records_to_create = []
            records_to_update = []

            for j, account_record in enumerate(company_accounts_data):
                self.logger.debug(f"    - معالجة حساب {j+1}/{total_accounts_in_company}: {account_record.get('code')} {account_record.get('name')} (ID: {account_record['id']})")
                source_id = account_record['id']
                source_code = account_record.get('code')
                source_name = account_record.get('name')

                if not source_code:
                    self.logger.warning(f"    - تخطي الحساب '{source_name}' (ID: {source_id}) لأنه لا يحتوي على كود في المصدر.")
                    continue

                transformed_data = self._transform_data(account_record, dest_company_id)
                transformed_data['company_ids'] = [(6, 0, [dest_company_id])]

                # 1. البحث في الوجهة مباشرة باستخدام `x_account_sync_id`.
                search_domain_x_sync_id = [('x_account_sync_id', '=', str(source_id))]
                existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

                if existing_record_by_x_sync_id:
                    destination_id = existing_record_by_x_sync_id[0]
                    records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
                else:
                    # 2. إذا لم يتم العثور عليه عبر `x_account_sync_id`، حاول البحث بالكود ومعرف الشركة.
                    search_domain_by_code = [
                        ('code', '=', source_code),
                        ('company_ids', 'in', [dest_company_id])
                    ]
                    existing_record_by_code = self.dest[self.MODEL].search(search_domain_by_code, limit=1)

                    if existing_record_by_code:
                        destination_id = existing_record_by_code[0]
                        transformed_data['x_account_sync_id'] = str(source_id)
                        records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
                    else:
                        # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                        transformed_data['x_account_sync_id'] = str(source_id)
                        records_to_create.append({'data': transformed_data, 'source_id': source_id})
            
            self._batch_sync_records(records_to_create, records_to_update)
            
        self.logger.info("اكتملت مزامنة شجرة الحسابات.")

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
                    self.activity_logger.info(f"    - تم إنشاء حساب جديد في الوجهة بمعرف ID: {new_destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات الحسابات الجديدة دفعيًا. الخطأ: {e}")

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
                    self.activity_logger.info(f"    - تم تحديث حساب موجود في الوجهة ID: {destination_id} من المصدر ID: {source_id}")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات الحسابات دفعيًا. الخطأ: {e}")

        self.logger.info("اكتملت المزامنة الدفعية للحسابات.")

        self._handle_deletions()

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف الحسابات...")
        
        # 1. جلب جميع معرفات المصدر المخزنة محليًا لـ account.account.
        mapped_source_ids = self.key_manager.get_all_source_ids_for_model(self.MODEL)
        self.logger.debug(f"  - تم العثور على {len(mapped_source_ids)} معرف مصدر mapped لـ {self.MODEL}.")

        if not mapped_source_ids:
            self.logger.info("  - لا توجد معرفات مصدر mapped لـ account.account. تخطي معالجة الحذف.")
            return

        # 2. جلب جميع معرفات account.account النشطة من نظام المصدر.
        active_source_ids = self.source[self.MODEL].search([])
        self.logger.debug(f"  - تم العثور على {len(active_source_ids)} معرف account.account نشط في المصدر.")

        # 3. تحديد السجلات التي تم حذفها في المصدر (موجودة في mapped_source_ids ولكن ليست في active_source_ids).
        deleted_source_ids = [sid for sid in mapped_source_ids if sid not in active_source_ids]
        self.logger.info(f"  - تم تحديد {len(deleted_source_ids)} سجل account.account للحذف (الأرشفة) في الوجهة.")

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
                    self.activity_logger.info(f"    - تم أرشفة الحساب ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة الحساب ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ account.account المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف الحسابات.")

    def _sync_record(self, source_record, dest_company_id):
        """
        هذه الدالة لم تعد تستخدم بشكل مباشر للمزامنة الفردية بعد التحول للمزامنة الدفعية.
        يمكن إزالتها أو تعديلها لتناسب أي استخدامات مستقبلية.
        """
        self.logger.warning("الدالة _sync_record تم استدعاؤها ولكنها لم تعد تستخدم للمزامنة الفردية. يرجى التحقق.")
        pass

    def _sync_record(self, source_record, dest_company_id):
        """
        مزامنة سجل حساب فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_account_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        """
        source_id = source_record['id']
        source_code = source_record.get('code')
        source_name = source_record.get('name')

        # لا نبحث عن الحسابات التي ليس لها كود لأنها غير موثوقة.
        if not source_code:
            self.logger.warning(f"    - تخطي الحساب '{source_name}' (ID: {source_id}) لأنه لا يحتوي على كود في المصدر.")
            return

        transformed_data = self._transform_data(source_record, dest_company_id)
        # تعيين `company_ids` بشكل صريح لربط الحساب بالشركة الصحيحة في الوجهة.
        transformed_data['company_ids'] = [(6, 0, [dest_company_id])]

        # 1. البحث في الوجهة مباشرة باستخدام `x_account_sync_id`.
        search_domain_x_sync_id = [('x_account_sync_id', '=', str(source_id))]
        existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_by_x_sync_id:
            # وجدناه عبر `x_account_sync_id`، قم بتحديثه.
            destination_id = existing_record_by_x_sync_id[0]
            self.logger.info(f"    - تحديث حساب موجود عبر x_account_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            try:
                self.dest[self.MODEL].write([destination_id], transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                self.logger.debug(f"    - تم تحديث سجل الوجهة ID: {destination_id} وتم تسجيل الربط.")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث الحساب ID {source_id} (عبر x_account_sync_id). الخطأ: {e}")
        else:
            # 2. إذا لم يتم العثور عليه عبر `x_account_sync_id`، حاول البحث بالكود ومعرف الشركة.
            search_domain_by_code = [
                ('code', '=', source_code),
                ('company_ids', 'in', [dest_company_id])
            ]
            existing_record_by_code = self.dest[self.MODEL].search(search_domain_by_code, limit=1)

            if existing_record_by_code:
                # وجدناه عبر الكود ومعرف الشركة، قم بالتحديث وتعيين `x_account_sync_id`.
                destination_id = existing_record_by_code[0]
                self.logger.info(f"    - تحديث حساب موجود عبر الكود. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
                try:
                    self.dest[self.MODEL].write([destination_id], transformed_data)
                    # تعيين `x_account_sync_id` لهذا السجل إذا تم العثور عليه بالاسم.
                    self.dest[self.MODEL].write([destination_id], {'x_account_sync_id': str(source_id)}) 
                    # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                    self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                    self.logger.debug(f"    - تم تحديث سجل الوجهة ID: {destination_id} وتم تسجيل الربط.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في تحديث الحساب ID {source_id} (عبر الكود). الخطأ: {e}")
            else:
                # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                transformed_data['x_account_sync_id'] = str(source_id) # تأكد من تعيين `x_account_sync_id` للسجلات الجديدة.
                self.logger.info(f"    - إنشاء حساب جديد للمصدر ID: {source_id} تحت الشركة ID: {dest_company_id}")
                try:
                    new_destination_id = self.dest[self.MODEL].create(transformed_data)
                    # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                    self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                    self.logger.info(f"    - تم إنشاء حساب جديد في الوجهة بمعرف ID: {new_destination_id} وتم تسجيل الربط.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في إنشاء الحساب ID {source_id}. الخطأ: {e}")

    def _transform_data(self, source_record, dest_company_id):
        """
        تحويل بيانات الحساب من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # معالجة نوع الحساب (نقل مباشر للقيمة).
        # اسم الحقل في الإصدارات الحديثة هو 'account_type'.
        if source_record.get('account_type'):
            data_to_sync['account_type'] = source_record['account_type']
        
        # التأكد من وجود الكود دائمًا.
        self.logger.debug(f"          - Code before transformation: {data_to_sync.get('code')}")
        if not data_to_sync.get('code'):
            data_to_sync['code'] = f"SYNC_{source_record['id']}"
        self.logger.debug(f"          - Code after transformation: {data_to_sync['code']}")

        # إزالة `company_ids` من سجل المصدر إذا كان موجودًا، حيث سيتم تعيينه بشكل صريح في `_sync_record`.
        data_to_sync.pop('company_ids', None)
        # إزالة `company_id` بشكل صريح في حال وجوده.
        data_to_sync.pop('company_id', None)

        return data_to_sync