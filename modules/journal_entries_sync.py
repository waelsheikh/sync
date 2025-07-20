# -*- coding: utf-8 -*-
"""
المرحلة 12: وحدة مزامنة قيود اليومية
modules/journal_entries_sync.py

الغرض:
- مزامنة قيود اليومية اليدوية (account.move with move_type='entry').
- هذه الوحدة ضرورية للأرصدة الافتتاحية وقيود التسوية.
"""

class JournalEntrySyncModule:
    """
    وحدة متخصصة لمزامنة قيود اليومية اليدوية (account.move).
    """
    MODEL = 'account.move'
    # جلب القيود المرحلة من نوع 'قيد يومية' فقط
    DOMAIN = [
        ('state', '=', 'posted'),
        ('move_type', '=', 'entry')
    ]
    FIELDS_TO_SYNC = [
        'id', 'name', 'date', 'ref', 'journal_id', 'line_ids'
    ]
    LINE_FIELDS = [
        'name', 'partner_id', 'account_id', 'debit', 'credit'
    ]

    def __init__(self, source_conn, dest_conn, key_manager):
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        print("تم تهيئة وحدة مزامنة قيود اليومية.")

    def run(self):
        print("بدء مزامنة قيود اليومية...")
        
        source_ids = self.source.env[self.MODEL].search(self.DOMAIN)
        source_data = self.source.env[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} قيد يومية في المصدر.")

        for record in source_data:
            print(f"  - معالجة قيد {record.get('name')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة قيود اليومية.")

    def _sync_record(self, source_record):
        source_id = source_record['id']
        destination_id = self.key_manager.get_destination_id(self.MODEL, source_id)
        
        if destination_id:
            print(f"    - القيد ID {source_id} موجود بالفعل في الوجهة. سيتم تخطيه.")
            return

        transformed_data = self._transform_data(source_record)
        
        if not transformed_data:
            print(f"    - فشل تحويل بيانات القيد ID {source_id}. سيتم تخطيه.")
            return

        transformed_data['x_sync_id'] = f"{self.MODEL},{source_id}"
        print(f"    - إنشاء قيد جديد للمصدر ID: {source_id}")
        
        try:
            new_destination_id = self.dest.env[self.MODEL].create(transformed_data)
            self.dest.env[self.MODEL].browse(new_destination_id).post()
            self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
            print(f"    - تم إنشاء القيد ID {new_destination_id} وترحيله. تم تسجيل الربط.")
        except Exception as e:
            print(f"    - [خطأ فادح] فشل في إنشاء القيد ID {source_id}. الخطأ: {e}")

    def _transform_data(self, source_record):
        data_to_sync = {
            'move_type': 'entry',
            'ref': source_record.get('ref'),
            'date': source_record.get('date'),
        }

        # ربط دفتر اليومية
        source_journal_id = source_record['journal_id'][0]
        dest_journal_id = self.key_manager.get_destination_id('account.journal', source_journal_id)
        if not dest_journal_id: return None
        data_to_sync['journal_id'] = dest_journal_id

        # تحويل السطور
        line_ids_data = self.source.env['account.move.line'].read(source_record['line_ids'], self.LINE_FIELDS)
        transformed_lines = []
        for line in line_ids_data:
            transformed_line = {
                'name': line['name'],
                'debit': line['debit'],
                'credit': line['credit'],
            }
            # ربط الحساب
            source_acc_id = line['account_id'][0]
            dest_acc_id = self.key_manager.get_destination_id('account.account', source_acc_id)
            if not dest_acc_id: 
                print(f"      - خطأ في السطر: الحساب ID {source_acc_id} غير موجود.")
                return None
            transformed_line['account_id'] = dest_acc_id
            
            # ربط الشريك (إذا كان موجوداً)
            if line.get('partner_id'):
                source_partner_id = line['partner_id'][0]
                dest_partner_id = self.key_manager.get_destination_id('res.partner', source_partner_id)
                if dest_partner_id:
                    transformed_line['partner_id'] = dest_partner_id

            transformed_lines.append((0, 0, transformed_line))
            
        data_to_sync['line_ids'] = transformed_lines
        return data_to_sync
