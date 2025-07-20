# -*- coding: utf-8 -*-
"""
المرحلة 7: وحدة مزامنة شجرة الحسابات
modules/accounts_sync.py

الغرض:
- مزامنة شجرة الحسابات (account.account) من المصدر إلى الوجهة.
- هذه الوحدة بسيطة نسبيًا لأن الحسابات لا تحتوي على علاقات معقدة كثيرة.
"""

class AccountSyncModule:
    """
    وحدة متخصصة لمزامنة شجرة الحسابات (account.account).
    """
    MODEL = 'account.account'
    # الحقول الأساسية للحساب. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'code', 'user_type_id', 'reconcile', 'company_id'
    ]

    def __init__(self, source_conn, dest_conn, key_manager):
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        # إضافة حقل المزامنة المخصص إلى قائمة الحقول المطلوبة في الوجهة
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_sync_id']
        print("تم تهيئة وحدة مزامنة شجرة الحسابات.")

    def run(self):
        print("بدء مزامنة شجرة الحسابات...")
        
        source_ids = self.source.env[self.MODEL].search([])
        source_data = self.source.env[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} حساب في المصدر.")

        for i, record in enumerate(source_data):
            print(f"  - معالجة حساب {i+1}/{total_records}: {record.get('code')} {record.get('name')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة شجرة الحسابات.")

    def _sync_record(self, source_record):
        source_id = source_record['id']
        
        # نستخدم "الكود" كمفتاح فريد للبحث في الوجهة، لأنه أكثر موثوقية من المعرف.
        # هذا يضمن عدم إنشاء حسابات مكررة إذا كانت موجودة بالفعل في شجرة حسابات Odoo Online الافتراضية.
        code = source_record.get('code')
        dest_id_found = self.dest.env[self.MODEL].search([('code', '=', code)], limit=1)

        transformed_data = self._transform_data(source_record)

        if dest_id_found:
            destination_id = dest_id_found[0]
            print(f"    - الحساب موجود بالفعل في الوجهة (Code: {code}). سيتم تحديثه. ID: {destination_id}")
            self.dest.env[self.MODEL].write([destination_id], transformed_data)
            # التأكد من تسجيل الربط في حال لم يكن مسجلاً من قبل
            self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
        else:
            # إنشاء (Create)
            transformed_data['x_sync_id'] = f"{self.MODEL},{source_id}"
            print(f"    - إنشاء حساب جديد للمصدر ID: {source_id}")
            new_destination_id = self.dest.env[self.MODEL].create(transformed_data)
            self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
            print(f"    - تم إنشاء حساب جديد في الوجهة بمعرف ID: {new_destination_id} وتم تسجيل الربط.")

    def _transform_data(self, source_record):
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # معالجة علاقة Many2One: user_type_id (نوع الحساب)
        if data_to_sync.get('user_type_id'):
            # نوع الحساب يُعرّف بواسطة معرف XML خارجي، وهو غالبًا ما يكون متطابقًا بين الأنظمة.
            # سنقوم بالبحث باستخدام الاسم كضمان.
            user_type_name = data_to_sync['user_type_id'][1]
            dest_user_type_ids = self.dest.env['account.account.type'].search([('name', '=', user_type_name)], limit=1)
            if dest_user_type_ids:
                data_to_sync['user_type_id'] = dest_user_type_ids[0]
            else:
                data_to_sync.pop('user_type_id')
                print(f"    - تحذير: لم يتم العثور على نوع الحساب '{user_type_name}' في الوجهة.")

        # معالجة علاقة Many2One: company_id
        if data_to_sync.get('company_id'):
            # نفترض أن الشركات تمت مزامنتها مسبقًا أو أن المعرفات متطابقة (في حالة الشركة الواحدة)
            # في نظام متعدد الشركات، يجب استخدام key_manager هنا.
            # للتبسيط، سنفترض أننا نعمل على الشركة الرئيسية (id=1) أو أن المعرفات متطابقة.
            # هذا هو المكان الذي يصبح فيه key_manager للشركات ضروريًا.
            source_company_id = data_to_sync['company_id'][0]
            dest_company_id = self.key_manager.get_destination_id('res.company', source_company_id)
            if dest_company_id:
                data_to_sync['company_id'] = dest_company_id
            else:
                 # في حالة الشركة الواحدة، قد يكون المعرف متطابقًا (1)
                data_to_sync['company_id'] = source_company_id
                print(f"    - تحذير: لم يتم العثور على ربط للشركة ID {source_company_id}. سيتم استخدام المعرف نفسه.")

        return data_to_sync
