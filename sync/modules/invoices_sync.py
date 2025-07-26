# -*- coding: utf-8 -*-
"""
المرحلة 10: وحدة مزامنة الفواتير
modules/invoices_sync.py

الغرض:
- مزامنة الفواتير وفواتير الموردين (account.move) من المصدر إلى الوجهة.
- هذه هي الوحدة الأكثر تعقيدًا لأنها تعتمد على العديد من السجلات المترابطة
  (جهات الاتصال، الحسابات، دفاتر اليومية، المنتجات، الضرائب).
"""

import logging

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
        'product_id', 'name', 'quantity', 'price_unit', 'account_id', 'tax_ids', 'tax_line_id', 'write_date', 'move_id'
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

        self.logger = loggers.get("invoices_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة الفواتير.")

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

        # 2. تجهيز السجلات للمزامنة الدفعية.
        records_to_create = []
        records_to_update = []

        for i, record in enumerate(records_to_sync):
            self.logger.debug(f"  - معالجة فاتورة {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            source_id = record['id']
            
            # 1. البحث في الوجهة مباشرة باستخدام `x_move_sync_id`.
            search_domain_x_sync_id = [('x_move_sync_id', '=', str(source_id))]
            existing_record_ids = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

            if existing_record_ids:
                destination_id = existing_record_ids[0]
                transformed_data = self._transform_data(record, is_update=True)
                if not transformed_data:
                    self.logger.warning(f"    - فشل تحويل بيانات الفاتورة ID {source_id} للتحديث. سيتم تخطيها.")
                    continue
                records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
            else:
                transformed_data = self._transform_data(record, is_update=False)
                if not transformed_data:
                    self.logger.warning(f"    - فشل تحويل بيانات الفاتورة ID {source_id} للإنشاء. سيتم تخطيها.")
                    continue
                transformed_data['x_move_sync_id'] = str(source_id)
                records_to_create.append({'data': transformed_data, 'source_id': source_id})
        
        self._batch_sync_records(records_to_create, records_to_update)
            
        self.logger.info("اكتملت مزامنة الفواتير.")

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
                    self.activity_logger.info(f"    - تم إنشاء فاتورة جديدة في الوجهة بمعرف ID: {new_destination_id} من المصدر ID: {source_id}")
                    # Post the newly created invoice
                    self.dest[self.MODEL].browse([new_destination_id]).action_post()
                    self.activity_logger.info(f"    - تم ترحيل الفاتورة ID {new_destination_id} بعد الإنشاء.")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات الفواتير الجديدة دفعيًا. الخطأ: {e}")

        # تحديث السجلات الموجودة
        if records_to_update:
            self.logger.info(f"تحديث {len(records_to_update)} سجل موجود...")
            try:
                for record_data in records_to_update:
                    destination_id = record_data['id']
                    source_id = record_data['source_id']
                    data = record_data['data']

                    # Get current state of the invoice in destination
                    current_invoice = self.dest[self.MODEL].read([destination_id], ['state'])[0]
                    
                    # Unpost if currently posted
                    if current_invoice['state'] == 'posted':
                        self.logger.info(f"      - إلغاء ترحيل الفاتورة ID {destination_id} قبل التحديث.")
                        self.dest[self.MODEL].browse([destination_id]).button_draft()

                    self.dest[self.MODEL].write([destination_id], data)
                    self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                    self.activity_logger.info(f"    - تم تحديث فاتورة موجودة في الوجهة ID: {destination_id} من المصدر ID: {source_id}")

                    # Repost if it was originally posted
                    if current_invoice['state'] == 'posted':
                        self.logger.info(f"      - إعادة ترحيل الفاتورة ID {destination_id} بعد التحديث.")
                        self.dest[self.MODEL].browse([destination_id]).action_post()

            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات الفواتير دفعيًا. الخطأ: {e}")

        self.logger.info("اكتملت المزامنة الدفعية للفواتير.")

        self._handle_deletions()

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف الفواتير...")
        
        # 1. جلب جميع معرفات المصدر المخزنة محليًا لـ account.move.
        mapped_source_ids = self.key_manager.get_all_source_ids_for_model(self.MODEL)
        self.logger.debug(f"  - تم العثور على {len(mapped_source_ids)} معرف مصدر mapped لـ {self.MODEL}.")

        if not mapped_source_ids:
            self.logger.info("  - لا توجد معرفات مصدر mapped لـ account.move. تخطي معالجة الحذف.")
            return

        # 2. جلب جميع معرفات account.move النشطة من نظام المصدر.
        active_source_ids = self.source[self.MODEL].search([])
        self.logger.debug(f"  - تم العثور على {len(active_source_ids)} معرف account.move نشط في المصدر.")

        # 3. تحديد السجلات التي تم حذفها في المصدر (موجودة في mapped_source_ids ولكن ليست في active_source_ids).
        deleted_source_ids = [sid for sid in mapped_source_ids if sid not in active_source_ids]
        self.logger.info(f"  - تم تحديد {len(deleted_source_ids)} سجل account.move للحذف (الأرشفة) في الوجهة.")

        if not deleted_source_ids:
            self.logger.info("  - لا توجد سجلات محذوفة في المصدر تتطلب الأرشفة في الوجهة.")
            return

        # 4. أرشفة السجلات المحذوفة في الوجهة وإزالة الربط.
        for source_id in deleted_source_ids:
            destination_id = self.key_manager.get_destination_id(self.MODEL, source_id)
            if destination_id:
                try:
                    # أرشفة السجل في الوجهة (ضبط active = False).
                    # For account.move, we might need to unpost first if it's posted.
                    current_move = self.dest[self.MODEL].read([destination_id], ['state'])[0]
                    if current_move['state'] == 'posted':
                        self.logger.info(f"      - إلغاء ترحيل الفاتورة ID {destination_id} قبل الأرشفة.")
                        self.dest[self.MODEL].browse([destination_id]).button_draft()

                    self.dest[self.MODEL].write([destination_id], {'active': False})
                    self.key_manager.remove_mapping(self.MODEL, source_id)
                    self.activity_logger.info(f"    - تم أرشفة الفاتورة ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة الفاتورة ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ account.move المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف الفواتير.")

    def _sync_record(self, source_record):
        """
        هذه الدالة لم تعد تستخدم بشكل مباشر للمزامنة الفردية بعد التحول للمزامنة الدفعية.
        يمكن إزالتها أو تعديلها لتناسب أي استخدامات مستقبلية.
        """
        self.logger.warning("الدالة _sync_record تم استدعاؤها ولكنها لم تعد تستخدم للمزامنة الفردية. يرجى التحقق.")
        pass

    

    def _transform_data(self, source_record, is_update=False):
        """
        تحويل بيانات الفاتورة من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.
        يتضمن معالجة العلاقات (مثل partner_id, journal_id, account_id, tax_ids).

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            is_update (bool): علامة لتحديد ما إذا كانت العملية هي تحديث لسجل موجود.
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
        
        final_line_commands = []
        
        # إذا كانت هذه عملية تحديث، أضف الأمر لحذف كل البنود القديمة أولاً
        if is_update:
            final_line_commands.append((5, 0, 0))

        # قم ببناء أوامر إنشاء البنود الجديدة
        for line in line_ids_data:
            # تخطي السطور التي تمثل ضرائب تم إنشاؤها تلقائيًا (لها tax_line_id).
            # هذا يمنع إنشاء سطور ضرائب مكررة، حيث سيقوم Odoo بإنشائها بناءً على `tax_ids` في السطر الأصلي.
            if line.get('tax_line_id'):
                self.logger.debug(f"      - تخطي سطر ضريبة (ID: {line['id']}) لأنه سيتم إنشاؤه تلقائيًا في الوجهة.")
                continue

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
            
            final_line_commands.append((0, 0, transformed_line))

        if not final_line_commands or (is_update and len(final_line_commands) == 1):
            print("    - خطأ: لا يمكن إنشاء فاتورة بدون سطور.")
            return None
            
        data_to_sync['invoice_line_ids'] = final_line_commands
        
        return data_to_sync
