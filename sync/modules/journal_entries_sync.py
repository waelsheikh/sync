# -*- coding: utf-8 -*-
"""
المرحلة 12: وحدة مزامنة قيود اليومية
modules/journal_entries_sync.py

الغرض:
- مزامنة قيود اليومية اليدوية (account.move with move_type='entry').
- هذه الوحدة ضرورية للأرصدة الافتتاحية وقيود التسوية.
"""

import logging

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
        'id', 'name', 'date', 'ref', 'journal_id', 'line_ids', 'write_date'
    ]
    LINE_FIELDS = [
        'name', 'partner_id', 'account_id', 'debit', 'credit', 'tax_ids', 'tax_tag_ids', 'tax_repartition_line_id', 'write_date', 'move_id'
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

        self.logger = loggers.get("journal_entries_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة قيود اليومية.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة قيود اليومية...")
        
        # 1. البحث عن قيود اليومية المعدلة.
        last_sync_timestamp = self.last_sync_time
        domain_moves = self.DOMAIN + [('write_date', '>', last_sync_timestamp)]
        updated_move_ids = self.source[self.MODEL].search(domain_moves)

        # 2. البحث عن سطور قيود اليومية المعدلة.
        domain_lines = [('write_date', '>', last_sync_timestamp), ('move_id.move_type', '=', 'entry')]
        lines_data = self.source['account.move.line'].search_read(domain_lines, ['move_id'])

        # 3. الحصول على معرّفات القيود من السطور المعدلة.
        moves_from_lines = []
        if lines_data:
            moves_from_lines = list(set([line['move_id'][0] for line in lines_data if line.get('move_id')]))

        # 4. دمج القائمتين للحصول على قائمة فريدة من القيود التي يجب مزامنتها.
        all_journal_entry_ids_to_sync = list(set(updated_move_ids + moves_from_lines))

        print(f"تم العثور على {len(all_journal_entry_ids_to_sync)} قيد يومية معدل للمزامنة.")

        # إذا لم تكن هناك سجلات للمزامنة، قم بالخروج من الدالة.
        if not all_journal_entry_ids_to_sync:
            print("لا توجد سجلات جديدة أو معدلة للمزامنة.")
            print("اكتملت مزامنة قيود اليومية.")
            return
        
        # اقرأ البيانات الكاملة للسجلات التي تحتاج إلى مزامنة فقط.
        source_data = self.source[self.MODEL].read(all_journal_entry_ids_to_sync, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} قيد يومية في المصدر.")

        # 2. تجهيز السجلات للمزامنة الدفعية.
        records_to_create = []
        records_to_update = []

        for i, record in enumerate(source_data):
            self.logger.debug(f"  - معالجة قيد {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            source_id = record['id']
            
            transformed_data = self._transform_data(record)
            
            if not transformed_data:
                self.logger.warning(f"    - فشل تحويل بيانات القيد ID {source_id}. سيتم تخطيه.")
                continue

            # 1. البحث في الوجهة مباشرة باستخدام `x_move_sync_id`.
            search_domain_x_sync_id = [('x_move_sync_id', '=', str(source_id))]
            existing_record_ids = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

            if existing_record_ids:
                destination_id = existing_record_ids[0]
                records_to_update.append({'id': destination_id, 'data': transformed_data, 'source_id': source_id})
            else:
                transformed_data['x_move_sync_id'] = str(source_id)
                records_to_create.append({'data': transformed_data, 'source_id': source_id})
        
        self._batch_sync_records(records_to_create, records_to_update)
            
        self.logger.info("اكتملت مزامنة قيود اليومية.")

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
                    self.activity_logger.info(f"    - تم إنشاء قيد يومية جديد في الوجهة بمعرف ID: {new_destination_id} من المصدر ID: {source_id}")
                    # Post the newly created journal entry
                    self.dest[self.MODEL].browse([new_destination_id]).action_post()
                    self.activity_logger.info(f"    - تم ترحيل القيد ID {new_destination_id} بعد الإنشاء.")
            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات قيود اليومية الجديدة دفعيًا. الخطأ: {e}")

        # تحديث السجلات الموجودة
        if records_to_update:
            self.logger.info(f"تحديث {len(records_to_update)} سجل موجود...")
            try:
                for record_data in records_to_update:
                    destination_id = record_data['id']
                    source_id = record_data['source_id']
                    data = record_data['data']

                    # Get current state of the journal entry in destination
                    current_journal_entry = self.dest[self.MODEL].read([destination_id], ['state'])[0]
                    
                    # Unpost if currently posted
                    if current_journal_entry['state'] == 'posted':
                        self.logger.info(f"      - إلغاء ترحيل القيد ID {destination_id} قبل التحديث.")
                        self.dest[self.MODEL].browse([destination_id]).button_draft()

                    self.dest[self.MODEL].write([destination_id], data)
                    self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                    self.activity_logger.info(f"    - تم تحديث قيد يومية موجود في الوجهة ID: {destination_id} من المصدر ID: {source_id}")

                    # Repost if it was originally posted
                    if current_journal_entry['state'] == 'posted':
                        self.logger.info(f"      - إعادة ترحيل القيد ID {destination_id} بعد التحديث.")
                        self.dest[self.MODEL].browse([destination_id]).action_post()

            except Exception as e:
                self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات قيود اليومية دفعيًا. الخطأ: {e}")

        self.logger.info("اكتملت المزامنة الدفعية لقيود اليومية.")

        self._handle_deletions()

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف قيود اليومية...")
        
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
                        self.logger.info(f"      - إلغاء ترحيل القيد ID {destination_id} قبل الأرشفة.")
                        self.dest[self.MODEL].browse([destination_id]).button_draft()

                    self.dest[self.MODEL].write([destination_id], {'active': False})
                    self.key_manager.remove_mapping(self.MODEL, source_id)
                    self.activity_logger.info(f"    - تم أرشفة القيد ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة القيد ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ account.move المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف قيود اليومية.")

    def _sync_record(self, source_record):
        """
        هذه الدالة لم تعد تستخدم بشكل مباشر للمزامنة الفردية بعد التحول للمزامنة الدفعية.
        يمكن إزالتها أو تعديلها لتناسب أي استخدامات مستقبلية.
        """
        self.logger.warning("الدالة _sync_record تم استدعاؤها ولكنها لم تعد تستخدم للمزامنة الفردية. يرجى التحقق.")
        pass

    def _sync_record(self, source_record):
        """
        مزامنة سجل قيد يومية فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_move_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        """
        source_id = source_record['id']
        
        # تحويل البيانات لتكون متوافقة مع Odoo API.
        transformed_data = self._transform_data(source_record)
        
        if not transformed_data:
            print(f"    - فشل تحويل بيانات القيد ID {source_id}. سيتم تخطيه.")
            return

        # 1. البحث في الوجهة مباشرة باستخدام `x_move_sync_id`.
        search_domain_x_sync_id = [('x_move_sync_id', '=', str(source_id))]
        existing_record_ids = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_ids:
            # تحديث (Update): السجل موجود بالفعل في الوجهة.
            destination_id = existing_record_ids[0]
            print(f"    - تحديث قيد يومية موجود عبر x_move_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            
            try:
                # جلب الحالة الحالية لقيد اليومية في الوجهة.
                current_journal_entry = self.dest[self.MODEL].read([destination_id], ['state'])[0]
                
                # إلغاء ترحيل قيد اليومية إذا كان مرحّلاً حاليًا.
                # هذا ضروري لتعديل قيود اليومية التي تم ترحيلها في Odoo.
                if current_journal_entry['state'] == 'posted':
                    print(f"      - إلغاء ترحيل القيد ID {destination_id} قبل التحديث.")
                    self.dest[self.MODEL].browse([destination_id]).button_draft()

                # تحديث بيانات قيد اليومية.
                self.dest[self.MODEL].write([destination_id], transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                print(f"      - تم تحديث بيانات القيد ID {destination_id}.")

                # إعادة ترحيل قيد اليومية إذا كان مرحّلاً في الأصل.
                if current_journal_entry['state'] == 'posted':
                    print(f"      - إعادة ترحيل القيد ID {destination_id} بعد التحديث.")
                    self.dest[self.MODEL].browse([destination_id]).action_post()

            except Exception as e:
                # معالجة الأخطاء أثناء تحديث قيد اليومية.
                print(f"    - [خطأ فادح] فشل في تحديث القيد ID {source_id} (عبر x_move_sync_id). الخطأ: {e}")
        else:
            # إنشاء (Create): السجل غير موجود في الوجهة.
            # إضافة معرف المصدر إلى الحقل المخصص `x_move_sync_id` في الوجهة.
            transformed_data['x_move_sync_id'] = str(source_id)
            
            print(f"    - إنشاء قيد جديد للمصدر ID: {source_id}")
            
            try:
                new_destination_id = self.dest[self.MODEL].create(transformed_data)
                # بعد الإنشاء، قد تحتاج إلى تنفيذ إجراء "ترحيل" (post) لقيد اليومية.
                self.dest[self.MODEL].browse([new_destination_id]).action_post()
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                print(f"    - تم إنشاء القيد ID {new_destination_id} وترحيله.")
            except Exception as e:
                # معالجة الأخطاء أثناء إنشاء قيد اليومية.
                print(f"    - [خطأ فادح] فشل في إنشاء القيد ID {source_id}. الخطأ: {e}")

    def _transform_data(self, source_record):
        """
        تحويل بيانات قيد اليومية من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.
        يتضمن معالجة العلاقات (مثل journal_id, account_id, partner_id).

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        final_dest_company_id = 1 # القيمة الافتراضية لمعرف الشركة (عادةً الشركة الرئيسية).

        data_to_sync = {
            'move_type': 'entry',
            'ref': source_record.get('ref'),
            'date': source_record.get('date'),
            'x_original_source_id': str(source_record['id']),
            'x_original_write_date': source_record['write_date']
        }

        # ربط دفتر اليومية.
        source_journal_id = source_record['journal_id'][0]
        # البحث عن معرف دفتر اليومية المقابل في الوجهة باستخدام `x_journal_sync_id`.
        dest_journal_ids_in_dest = self.dest['account.journal'].search([('x_journal_sync_id', '=', str(source_journal_id))], limit=1)

        # جلب معرف الشركة من دفتر اليومية في الوجهة.
        if dest_journal_ids_in_dest:
            dest_journal_id = dest_journal_ids_in_dest[0]
            journal_info = self.dest['account.journal'].read([dest_journal_id], ['company_id'])
            if journal_info and journal_info[0].get('company_id'):
                final_dest_company_id = journal_info[0]['company_id'][0]
        else:
            print(f"    - خطأ: دفتر اليومية ID {source_journal_id} غير موجود في الوجهة (لا يوجد x_journal_sync_id مطابق). لا يمكن مزامنة هذا القيد.")
            return None

        data_to_sync['journal_id'] = dest_journal_id

        # تحويل السطور.
        line_ids_data = self.source['account.move.line'].read(source_record['line_ids'], self.LINE_FIELDS)
        transformed_lines = []
        for line in line_ids_data:
            # --- الشرط الأهم: تجاهل بنود الضرائب التي أنشأها Odoo تلقائيًا ---
            if line.get('tax_repartition_line_id'):
                self.logger.debug(f"      - تجاهل بند الضريبة (ID: {line['id']}) لأنه سيتم إعادة حسابه في الوجهة.")
                continue

            transformed_line = {
                'name': line['name'],
                'debit': line['debit'],
                'credit': line['credit'],
            }
            # ربط الحساب.
            source_acc_id = line['account_id'][0]
            # البحث عن معرف الحساب المقابل في الوجهة باستخدام `x_account_sync_id`.
            dest_acc_ids_in_dest = self.dest['account.account'].search([('x_account_sync_id', '=', str(source_acc_id))], limit=1)
            if not dest_acc_ids_in_dest:
                print(f"      - خطأ في السطر: الحساب ID {source_acc_id} غير موجود في الوجهة (لا يوجد x_account_sync_id مطابق). سيتم تخطي هذا السطر.")
                return None # تخطي هذا السطر

            dest_acc_id = dest_acc_ids_in_dest[0]
            # التحقق مما إذا كان الحساب المربوط ينتمي إلى نفس شركة قيد اليومية.
            account_info = self.dest['account.account'].read([dest_acc_id], ['company_ids'])[0]
            account_company_ids = account_info.get('company_ids', [])

            if final_dest_company_id not in account_company_ids:
                print(f"      - خطأ في السطر: الحساب ID {source_acc_id} ينتمي لشركة مختلفة في الوجهة. لا يمكن مزامنة هذا السطر.")
                return None # تخطي هذا السطر إذا كان هناك عدم تطابق في الشركة.

            transformed_line['account_id'] = dest_acc_id
            
            # ربط الشريك (إذا كان موجوداً).
            if line.get('partner_id'):
                source_partner_id = line['partner_id'][0]
                # البحث عن معرف الشريك المقابل في الوجهة باستخدام `x_partner_sync_id`.
                dest_partner_ids_in_dest = self.dest['res.partner'].search([('x_partner_sync_id', '=', str(source_partner_id))], limit=1)
                if dest_partner_ids_in_dest:
                    transformed_line['partner_id'] = dest_partner_ids_in_dest[0]

            # --- تعديل حاسم ---
            # دائماً أرسل tax_ids و tax_tag_ids لمنع الأتمتة في Odoo

            # 1. ربط الضرائب (tax_ids).
            source_tax_ids = line.get('tax_ids', [])
            destination_tax_ids = []
            for tax_id in source_tax_ids:
                # البحث عن معرف الضريبة المقابل في الوجهة باستخدام `x_tax_sync_id`.
                dest_tax_ids_in_dest = self.dest['account.tax'].search([('x_tax_sync_id', '=', str(tax_id))], limit=1)
                if dest_tax_ids_in_dest:
                    destination_tax_ids.append(dest_tax_ids_in_dest[0])
                else:
                    self.logger.warning(f"      - تحذير في السطر: الضريبة ID {tax_id} غير موجودة في الوجهة. سيتم تخطيها.")
            # أرسل القائمة دائماً، حتى لو كانت فارغة.
            transformed_line['tax_ids'] = [(6, 0, destination_tax_ids)]

            # 2. ربط علامات الضرائب (tax_tag_ids).
            source_tax_tag_ids = line.get('tax_tag_ids', [])
            destination_tax_tag_ids = []
            for tag_id in source_tax_tag_ids:
                # البحث عن علامات الضرائب يتطلب مطابقة الاسم والنوع والبلد
                source_tag = self.source['account.account.tag'].read(tag_id, ['name', 'applicability', 'country_id'])
                if source_tag:
                    search_domain = [('name', '=', source_tag['name']), ('applicability', '=', source_tag['applicability'])]
                    if source_tag.get('country_id'):
                        # إذا كانت العلامة مرتبطة ببلد، ابحث عن بلد مطابق في الوجهة
                        source_country_code = self.source['res.country'].read(source_tag['country_id'][0], ['code'])['code']
                        dest_country_id = self.dest['res.country'].search([('code', '=', source_country_code)], limit=1)
                        if dest_country_id:
                            search_domain.append(('country_id', '=', dest_country_id[0]))
                        else:
                            search_domain.append(('country_id', '=', False)) # أو تعامل مع الحالة بشكل مختلف
                    else:
                        search_domain.append(('country_id', '=', False))
                    
                    dest_tag_id = self.dest['account.account.tag'].search(search_domain, limit=1)
                    if dest_tag_id:
                        destination_tax_tag_ids.append(dest_tag_id[0])
                    else:
                        self.logger.warning(f"      - تحذير في السطر: علامة الضريبة '{source_tag['name']}' غير موجودة في الوجهة. سيتم تخطيها.")
            # أرسل القائمة دائماً، حتى لو كانت فارغة.
            transformed_line['tax_tag_ids'] = [(6, 0, destination_tax_tag_ids)]

            transformed_lines.append((0, 0, transformed_line))
            
        data_to_sync['line_ids'] = transformed_lines
        return data_to_sync
