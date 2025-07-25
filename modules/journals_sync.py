# -*- coding: utf-8 -*-
"""
المرحلة 8: وحدة مزامنة دفاتر اليومية
modules/journals_sync.py

الغرض:
- مزامنة دفاتر اليومية (account.journal) من المصدر إلى الوجهة.
- تعتمد هذه الوحدة على وجود شجرة الحسابات في الوجهة.
"""

class JournalSyncModule:
    """
    وحدة متخصصة لمزامنة دفاتر اليومية (account.journal).
    """
    MODEL = 'account.journal'
    # الحقول الأساسية لدفتر اليومية. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'code', 'type', 'default_account_id', 'company_id'
    ]

    def __init__(self, source_conn, dest_conn, key_manager, last_sync_time):
        """
        تهيئة الوحدة بالخدمات التي تحتاجها من المحرك.

        Args:
            source_conn: كائن اتصال Odoo API للمصدر.
            dest_conn: كائن اتصال Odoo API للوجهة.
            key_manager: كائن مدير مفاتيح المزامنة.
            last_sync_time: آخر طابع زمني للمزامنة الناجحة.
        """
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        self.last_sync_time = last_sync_time
        # إضافة حقل المزامنة المخصص إلى قائمة الحقول المطلوبة في الوجهة.
        # هذا الحقل يستخدم لربط السجلات بين المصدر والوجهة.
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_journal_sync_id']
        print("تم تهيئة وحدة مزامنة دفاتر اليومية.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة دفاتر اليومية...")
        
        # 1. استخراج البيانات من المصدر.
        # جلب فقط السجلات التي تم تعديلها منذ آخر مزامنة (باستخدام write_date).
        source_ids = self.source[self.MODEL].search([('write_date', '>', self.last_sync_time)])
        source_data = self.source[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} دفتر يومية في المصدر.")

        # 2. المرور على كل سجل ومزامنته.
        for i, record in enumerate(source_data):
            print(f"  - معالجة دفتر {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة دفاتر اليومية.")

    def _sync_record(self, source_record):
        """
        مزامنة سجل دفتر يومية فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_journal_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        """
        source_id = source_record['id']
        code = source_record.get('code')

        transformed_data = self._transform_data(source_record)
        if not transformed_data:
            return # توقف إذا فشل التحويل (مثلاً لم يتم العثور على حساب أساسي).

        # 1. البحث في الوجهة مباشرة باستخدام `x_journal_sync_id`.
        search_domain_x_sync_id = [('x_journal_sync_id', '=', str(source_id))]
        existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_by_x_sync_id:
            # وجدناه عبر `x_journal_sync_id`، قم بتحديثه.
            destination_id = existing_record_by_x_sync_id[0]
            print(f"    - تحديث دفتر يومية موجود عبر x_journal_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            update_data = transformed_data.copy()
            update_data.pop('type', None) # حقل 'type' ليس قابلاً للتحديث بعد الإنشاء.
            self.dest[self.MODEL].write([destination_id], update_data)
            # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
            self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
        else:
            # 2. إذا لم يتم العثور عليه عبر `x_journal_sync_id`، حاول البحث بالكود ومعرف الشركة.
            search_domain_by_code = [
                ('code', '=', code),
                ('type', '=', source_record.get('type')),
                ('company_id', '=', transformed_data['company_id'])
            ]
            existing_record_by_code = self.dest[self.MODEL].search(search_domain_by_code, limit=1)

            if existing_record_by_code:
                # وجدناه عبر الكود ومعرف الشركة، قم بالتحديث وتعيين `x_journal_sync_id`.
                destination_id = existing_record_by_code[0]
                print(f"    - تحديث دفتر يومية موجود عبر الكود. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
                update_data = transformed_data.copy()
                update_data.pop('type', None) # حقل 'type' ليس قابلاً للتحديث بعد الإنشاء.
                self.dest[self.MODEL].write([destination_id], update_data)
                # تعيين `x_journal_sync_id` لهذا السجل إذا تم العثور عليه بالاسم.
                self.dest[self.MODEL].write([destination_id], {'x_journal_sync_id': str(source_id)}) 
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
            else:
                # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                transformed_data['x_journal_sync_id'] = str(source_id) # تأكد من تعيين `x_journal_sync_id` للسجلات الجديدة.
                print(f"    - إنشاء دفتر يومية جديد للمصدر ID: {source_id}")
                new_destination_id = self.dest[self.MODEL].create(transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                print(f"    - تم إنشاء دفتر جديد في الوجهة بمعرف ID: {new_destination_id}.")

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
            print(f"    - تحذير: حقل 'type' مفقود من سجل المصدر لدفتر اليومية '{source_record.get('name')}'.")

        # جلب معرف الشركة المقابل في الوجهة باستخدام `x_company_sync_id`.
        final_dest_company_id = 1 # القيمة الافتراضية لمعرف الشركة (عادةً الشركة الرئيسية).
        if data_to_sync.get('company_id'):
            source_company_id = data_to_sync['company_id'][0]
            dest_company_ids_in_dest = self.dest['res.company'].search([('x_company_sync_id', '=', str(source_company_id))], limit=1)
            if dest_company_ids_in_dest:
                final_dest_company_id = dest_company_ids_in_dest[0]
            else:
                print(f"    - تحذير: لم يتم العثور على الشركة ID {source_company_id} في الوجهة عبر x_company_sync_id. سيتم استخدام الشركة الافتراضية (ID 1).")
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
                    print(f"    - خطأ فادح: الحساب الافتراضي ID {source_account_id} لدفتر اليومية '{data_to_sync['name']}' ينتمي لشركة مختلفة في الوجهة. لا يمكن مزامنة هذا الدفتر.")
                    return None
            else:
                print(f"    - خطأ فادح: الحساب الافتراضي ID {source_account_id} لدفتر اليومية '{data_to_sync['name']}' غير موجود في الوجهة. لا يمكن مزامنة هذا الدفتر.")
                return None

        return data_to_sync