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
    FIELDS_TO_SYNC = [
        'id', 'name', 'code', 'type', 'default_account_id', 'company_id'
    ]

    def __init__(self, source_conn, dest_conn, key_manager):
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_sync_id']
        print("تم تهيئة وحدة مزامنة دفاتر اليومية.")

    def run(self):
        print("بدء مزامنة دفاتر اليومية...")
        
        source_ids = self.source.env[self.MODEL].search([])
        source_data = self.source.env[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} دفتر يومية في المصدر.")

        for i, record in enumerate(source_data):
            print(f"  - معالجة دفتر {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة دفاتر اليومية.")

    def _sync_record(self, source_record):
        source_id = source_record['id']
        code = source_record.get('code')

        # البحث في الوجهة باستخدام الكود والنوع لضمان الدقة
        dest_id_found = self.dest.env[self.MODEL].search([
            ('code', '=', code),
            ('type', '=', source_record.get('type'))
        ], limit=1)

        transformed_data = self._transform_data(source_record)
        if not transformed_data:
            return # توقف إذا فشل التحويل (مثلاً لم يتم العثور على حساب أساسي)

        if dest_id_found:
            destination_id = dest_id_found[0]
            print(f"    - دفتر اليومية موجود بالفعل في الوجهة (Code: {code}). سيتم تحديثه. ID: {destination_id}")
            self.dest.env[self.MODEL].write([destination_id], transformed_data)
            self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
        else:
            transformed_data['x_sync_id'] = f"{self.MODEL},{source_id}"
            print(f"    - إنشاء دفتر يومية جديد للمصدر ID: {source_id}")
            new_destination_id = self.dest.env[self.MODEL].create(transformed_data)
            self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
            print(f"    - تم إنشاء دفتر جديد في الوجهة بمعرف ID: {new_destination_id} وتم تسجيل الربط.")

    def _transform_data(self, source_record):
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # أهم خطوة: ربط الحساب الافتراضي (default_account_id)
        if data_to_sync.get('default_account_id'):
            source_account_id = data_to_sync['default_account_id'][0]
            dest_account_id = self.key_manager.get_destination_id('account.account', source_account_id)
            
            if dest_account_id:
                data_to_sync['default_account_id'] = dest_account_id
            else:
                print(f"    - خطأ فادح: الحساب الافتراضي ID {source_account_id} لدفتر اليومية '{data_to_sync['name']}' غير موجود في الوجهة. لا يمكن مزامنة هذا الدفتر.")
                return None # إرجاع None للإشارة إلى فشل التحويل

        # معالجة الشركة (مشابهة لما سبق)
        if data_to_sync.get('company_id'):
            source_company_id = data_to_sync['company_id'][0]
            dest_company_id = self.key_manager.get_destination_id('res.company', source_company_id)
            data_to_sync['company_id'] = dest_company_id or source_company_id

        return data_to_sync
