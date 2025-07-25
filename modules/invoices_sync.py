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
        'journal_id', 'move_type', 'state', 'invoice_line_ids', 'write_date'
    ]
    LINE_FIELDS = [
        'product_id', 'name', 'quantity', 'price_unit', 'account_id', 'tax_ids', 'write_date', 'move_id'
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
        print("تم تهيئة وحدة مزامنة الفواتير.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب الفواتير المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة الفواتير...")
        
        # اقرأ آخر وقت مزامنة من الملف.
        last_sync_timestamp = self.last_sync_time

        # 1. ابحث عن معرّفات الفواتير (الرؤوس) التي تم تعديلها.
        # يتم استخدام `DOMAIN` لفلترة نوع الفواتير المطلوبة.
        domain_moves = self.DOMAIN + [('write_date', '>', last_sync_timestamp)]
        updated_move_ids = self.source[self.MODEL].search(domain_moves)

        # 2. ابحث عن معرّفات سطور الفواتير التي تم تعديلها.
        # يتم البحث في `account.move.line` عن السطور التي تغيرت وتتبعها إلى الفاتورة الأم.
        domain_lines = [('write_date', '>', last_sync_timestamp), ('move_id.move_type', 'in', ['out_invoice', 'in_invoice'])]
        lines_data = self.source['account.move.line'].search_read(domain_lines, ['move_id'])

        # 3. استخرج معرّفات الفواتير الفريدة من السطور المعدلة.
        # هذا يضمن أننا نعالج الفاتورة الأم مرة واحدة فقط حتى لو تغيرت عدة سطور فيها.
        moves_from_lines = []
        if lines_data:
            moves_from_lines = list(set([line['move_id'][0] for line in lines_data if line.get('move_id')]))

        # 4. ادمج القائمتين معًا في قائمة واحدة فريدة من المعرّفات.
        # هذه القائمة تحتوي على جميع الفواتير التي تحتاج إلى مزامنة (سواء تغير رأسها أو أحد سطورها).
        all_invoice_ids_to_sync = list(set(updated_move_ids + moves_from_lines))

        print(f"تم العثور على {len(all_invoice_ids_to_sync)} فاتورة/قيد معدل للمزامنة.")

        # إذا لم تكن هناك سجلات للمزامنة، قم بالخروج من الدالة.
        if not all_invoice_ids_to_sync:
            print("لا توجد سجلات جديدة أو معدلة للمزامنة.")
            print("اكتملت مزامنة الفواتير.")
            return # للخروج من الدالة إذا لم يكن هناك شيء لعمله

        # اقرأ البيانات الكاملة للسجلات التي تحتاج إلى مزامنة فقط.
        # يتم جلب جميع الحقول المحددة في `FIELDS_TO_SYNC`.
        records_to_sync = self.source[self.MODEL].read(all_invoice_ids_to_sync, self.FIELDS_TO_SYNC)
        
        total_records = len(records_to_sync)
        print(f"--- معالجة دفعة من {total_records} فاتورة ---")

        # المرور على كل سجل فاتورة تم تحديده للمزامنة.
        for record in records_to_sync:
            print(f"  - معالجة فاتورة {record.get('name')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة الفواتير.")

    def _sync_record(self, source_record):
        """
        مزامنة سجل فاتورة فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_move_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        """
        source_id = source_record['id']
        
        # تحويل البيانات لتكون متوافقة مع Odoo API.
        transformed_data = self._transform_data(source_record)
        
        if not transformed_data:
            print(f"    - فشل تحويل بيانات الفاتورة ID {source_id}. سيتم تخطيها.")
            return

        # 1. البحث في الوجهة مباشرة باستخدام `x_move_sync_id`.
        # هذا يضمن أننا نعتمد على المعرف الفريد المخزن في Odoo الوجهة نفسه.
        search_domain_x_sync_id = [('x_move_sync_id', '=', str(source_id))]
        existing_record_ids = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_ids:
            # تحديث (Update): السجل موجود بالفعل في الوجهة.
            destination_id = existing_record_ids[0]
            print(f"    - تحديث فاتورة موجودة عبر x_move_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            
            try:
                # جلب الحالة الحالية للفاتورة في الوجهة.
                current_invoice = self.dest[self.MODEL].read([destination_id], ['state'])[0]
                
                # إلغاء ترحيل الفاتورة إذا كانت مرحّلة حاليًا.
                # هذا ضروري لتعديل الفواتير التي تم ترحيلها في Odoo.
                if current_invoice['state'] == 'posted':
                    print(f"      - إلغاء ترحيل الفاتورة ID {destination_id} قبل التحديث.")
                    self.dest[self.MODEL].browse([destination_id]).button_draft()

                # تحديث بيانات الفاتورة.
                self.dest[self.MODEL].write([destination_id], transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                print(f"      - تم تحديث بيانات الفاتورة ID {destination_id}.")

                # إعادة ترحيل الفاتورة إذا كانت مرحّلة في الأصل.
                if current_invoice['state'] == 'posted':
                    print(f"      - إعادة ترحيل الفاتورة ID {destination_id} بعد التحديث.")
                    self.dest[self.MODEL].browse([destination_id]).action_post()

            except Exception as e:
                # معالجة الأخطاء أثناء تحديث الفاتورة.
                print(f"    - [خطأ فادح] فشل في تحديث الفاتورة ID {source_id} (عبر x_move_sync_id). الخطأ: {e}")
        else:
            # إنشاء (Create): السجل غير موجود في الوجهة.
            # إضافة معرف المصدر إلى الحقل المخصص `x_move_sync_id` في الوجهة.
            transformed_data['x_move_sync_id'] = str(source_id)
            
            print(f"    - إنشاء فاتورة جديدة للمصدر ID: {source_id}")
            
            try:
                new_destination_id = self.dest[self.MODEL].create(transformed_data)
                # بعد الإنشاء، قد تحتاج إلى تنفيذ إجراء "ترحيل" (post) للفاتورة.
                self.dest[self.MODEL].browse([new_destination_id]).action_post()
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                print(f"    - تم إنشاء الفاتورة ID {new_destination_id} وترحيلها في الوجهة.")
            except Exception as e:
                # معالجة الأخطاء أثناء إنشاء الفاتورة.
                print(f"    - [خطأ فادح] فشل في إنشاء أو ترحيل الفاتورة ID {source_id} في الوجهة. الخطأ: {e}")

    def _transform_data(self, source_record):
        """
        تحويل بيانات الفاتورة من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.
        يتضمن معالجة العلاقات (مثل partner_id, journal_id, account_id, tax_ids).

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = {
            'move_type': source_record.get('move_type'),
            'state': 'draft', # يتم الإنشاء دائمًا كمسودة ثم يتم ترحيلها.
            'x_original_source_id': str(source_record['id']),
            'x_original_write_date': source_record['write_date']
        }

        # 1. ربط العميل (partner_id).
        if not source_record.get('partner_id'): return None
        source_partner_id = source_record['partner_id'][0]
        # البحث عن معرف العميل المقابل في الوجهة باستخدام `x_partner_sync_id`.
        dest_partner_ids_in_dest = self.dest['res.partner'].search([('x_partner_sync_id', '=', str(source_partner_id))], limit=1)
        if not dest_partner_ids_in_dest:
            print(f"    - خطأ: العميل ID {source_partner_id} غير موجود في الوجهة (لا يوجد x_partner_sync_id مطابق). سيتم تخطي الفاتورة.")
            return None
        data_to_sync['partner_id'] = dest_partner_ids_in_dest[0]

        # 2. ربط دفتر اليومية (journal_id).
        source_journal_id = source_record['journal_id'][0]
        # البحث عن معرف دفتر اليومية المقابل في الوجهة باستخدام `x_journal_sync_id`.
        dest_journal_ids_in_dest = self.dest['account.journal'].search([('x_journal_sync_id', '=', str(source_journal_id))], limit=1)
        if not dest_journal_ids_in_dest:
            print(f"    - خطأ: دفتر اليومية ID {source_journal_id} غير موجود في الوجهة (لا يوجد x_journal_sync_id مطابق). سيتم تخطي الفاتورة.")
            return None
        data_to_sync['journal_id'] = dest_journal_ids_in_dest[0]

        # 3. نسخ الحقول البسيطة (التواريخ).
        for field in ['invoice_date', 'date', 'invoice_date_due']:
            if source_record.get(field):
                data_to_sync[field] = source_record[field]
        
        # 4. تحويل سطور الفاتورة (invoice_line_ids).
        line_ids_data = self.source['account.move.line'].read(source_record['invoice_line_ids'], self.LINE_FIELDS)
        transformed_lines = []
        for line in line_ids_data:
            # تخطي السطور التي لا تمثل منتجًا (مثل سطور الضرائب).
            if not line.get('product_id'): continue

            transformed_line = {
                'name': line['name'],
                'quantity': line['quantity'],
                'price_unit': line['price_unit'],
            }
            # ربط الحساب.
            source_acc_id = line['account_id'][0]
            # البحث عن معرف الحساب المقابل في الوجهة باستخدام `x_account_sync_id`.
            dest_acc_ids_in_dest = self.dest['account.account'].search([('x_account_sync_id', '=', str(source_acc_id))], limit=1)
            if not dest_acc_ids_in_dest: 
                print(f"      - خطأ في السطر: الحساب ID {source_acc_id} غير موجود في الوجهة (لا يوجد x_account_sync_id مطابق). سيتم تخطي هذا السطر.")
                continue # تخطي هذا السطر
            transformed_line['account_id'] = dest_acc_ids_in_dest[0]
            
            # ربط الضرائب.
            source_tax_ids = line.get('tax_ids', [])
            destination_tax_ids = []
            for tax_id in source_tax_ids:
                # البحث عن معرف الضريبة المقابل في الوجهة باستخدام `x_tax_sync_id`.
                dest_tax_ids_in_dest = self.dest['account.tax'].search([('x_tax_sync_id', '=', str(tax_id))], limit=1)
                if dest_tax_ids_in_dest:
                    destination_tax_ids.append(dest_tax_ids_in_dest[0])
                else:
                    print(f"      - تحذير في السطر: الضريبة ID {tax_id} غير موجودة في الوجهة (لا يوجد x_tax_sync_id مطابق). سيتم تخطيها.")
            transformed_line['tax_ids'] = [(6, 0, destination_tax_ids)]
            
            transformed_lines.append((0, 0, transformed_line))

        if not transformed_lines:
            print("    - خطأ: لا يمكن إنشاء فاتورة بدون سطور.")
            return None
            
        data_to_sync['invoice_line_ids'] = transformed_lines
        
        return data_to_sync