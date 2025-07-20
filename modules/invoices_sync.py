# -*- coding: utf-8 -*-
"""
المرحلة 10: وحدة مزامنة الفواتير
modules/invoices_sync.py

الغرض:
- مزامنة الفواتير وفواتير الموردين (account.move) من المصدر إلى الوجهة.
- هذه هي الوحدة الأكثر تعقيدًا لأنها تعتمد على العديد من السجلات المترابطة
  (جهات الاتصال، الحسابات، دفاتر اليومية، المنتجات، الضرائب).
"""

class InvoiceSyncModule:
    """
    وحدة متخصصة لمزامنة الفواتير (account.move).
    """
    MODEL = 'account.move'
    # سنركز على الفواتير التي لم يتم دفعها بعد (لترحيل الأرصدة الافتتاحية)
    # ونوعها فواتير عملاء أو فواتير موردين
    DOMAIN = [
        ('payment_state', '!=', 'paid'),
        ('state', '=', 'posted'),
        ('move_type', 'in', ['out_invoice', 'in_invoice'])
    ]
    FIELDS_TO_SYNC = [
        'id', 'name', 'partner_id', 'invoice_date', 'date', 'invoice_date_due',
        'journal_id', 'move_type', 'state', 'invoice_line_ids'
    ]
    LINE_FIELDS = [
        'product_id', 'name', 'quantity', 'price_unit', 'account_id', 'tax_ids'
    ]

    def __init__(self, source_conn, dest_conn, key_manager):
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        print("تم تهيئة وحدة مزامنة الفواتير.")

    def run(self):
        print("بدء مزامنة الفواتير...")
        
        source_ids = self.source.env[self.MODEL].search(self.DOMAIN)
        # نقوم بمعالجة الفواتير على دفعات لتجنب استهلاك الذاكرة
        batch_size = 10
        for i in range(0, len(source_ids), batch_size):
            batch_ids = source_ids[i:i + batch_size]
            source_data = self.source.env[self.MODEL].read(batch_ids, self.FIELDS_TO_SYNC)
            
            total_records = len(source_data)
            print(f"--- معالجة دفعة من {total_records} فاتورة ---")

            for record in source_data:
                print(f"  - معالجة فاتورة {record.get('name')} (ID: {record['id']})")
                self._sync_record(record)
            
        print("اكتملت مزامنة الفواتير.")

    def _sync_record(self, source_record):
        source_id = source_record['id']
        
        destination_id = self.key_manager.get_destination_id(self.MODEL, source_id)
        
        if destination_id:
            print(f"    - الفاتورة ID {source_id} موجودة بالفعل في الوجهة. سيتم تخطي التحديث حاليًا.")
            # تحديث الفواتير يمكن أن يكون معقدًا، لذا سنتخطاه في هذا المثال
            return

        transformed_data = self._transform_data(source_record)
        
        if not transformed_data:
            print(f"    - فشل تحويل بيانات الفاتورة ID {source_id}. سيتم تخطيها.")
            return

        # إنشاء الفاتورة الجديدة
        transformed_data['x_sync_id'] = f"{self.MODEL},{source_id}"
        print(f"    - إنشاء فاتورة جديدة للمصدر ID: {source_id}")
        
        try:
            new_destination_id = self.dest.env[self.MODEL].create(transformed_data)
            # بعد الإنشاء، قد تحتاج إلى تنفيذ إجراء "ترحيل" (post)
            self.dest.env[self.MODEL].browse(new_destination_id).post()
            
            self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
            print(f"    - تم إنشاء الفاتورة ID {new_destination_id} وترحيلها في الوجهة. تم تسجيل الربط.")
        except Exception as e:
            print(f"    - [خطأ فادح] فشل في إنشاء أو ترحيل الفاتورة ID {source_id} في الوجهة. الخطأ: {e}")

    def _transform_data(self, source_record):
        data_to_sync = {
            'move_type': source_record.get('move_type'),
            'state': 'draft', # يتم الإنشاء دائمًا كمسودة ثم يتم ترحيلها
        }

        # 1. ربط العميل (partner_id)
        if not source_record.get('partner_id'): return None
        source_partner_id = source_record['partner_id'][0]
        dest_partner_id = self.key_manager.get_destination_id('res.partner', source_partner_id)
        if not dest_partner_id:
            print(f"    - خطأ: العميل ID {source_partner_id} غير موجود في الوجهة.")
            return None
        data_to_sync['partner_id'] = dest_partner_id

        # 2. ربط دفتر اليومية (journal_id)
        source_journal_id = source_record['journal_id'][0]
        dest_journal_id = self.key_manager.get_destination_id('account.journal', source_journal_id)
        if not dest_journal_id:
            print(f"    - خطأ: دفتر اليومية ID {source_journal_id} غير موجود في الوجهة.")
            return None
        data_to_sync['journal_id'] = dest_journal_id

        # 3. نسخ الحقول البسيطة (التواريخ)
        for field in ['invoice_date', 'date', 'invoice_date_due']:
            if source_record.get(field):
                data_to_sync[field] = source_record[field]
        
        # 4. تحويل سطور الفاتورة (invoice_line_ids)
        line_ids_data = self.source.env['account.move.line'].read(source_record['invoice_line_ids'], self.LINE_FIELDS)
        transformed_lines = []
        for line in line_ids_data:
            # تخطي السطور التي لا تمثل منتجًا (مثل سطور الضرائب)
            if not line.get('product_id'): continue

            transformed_line = {
                'name': line['name'],
                'quantity': line['quantity'],
                'price_unit': line['price_unit'],
            }
            # ربط الحساب
            source_acc_id = line['account_id'][0]
            dest_acc_id = self.key_manager.get_destination_id('account.account', source_acc_id)
            if not dest_acc_id: 
                print(f"      - خطأ في السطر: الحساب ID {source_acc_id} غير موجود.")
                continue # تخطي هذا السطر
            transformed_line['account_id'] = dest_acc_id
            
            # يمكنك إضافة منطق لمزامنة المنتجات والضرائب هنا بنفس الطريقة
            # للتبسيط، سنهملها الآن
            
            transformed_lines.append((0, 0, transformed_line))

        if not transformed_lines:
            print("    - خطأ: لا يمكن إنشاء فاتورة بدون سطور.")
            return None
            
        data_to_sync['invoice_line_ids'] = transformed_lines
        
        return data_to_sync