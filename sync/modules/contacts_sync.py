import logging

class ContactSyncModule:
    MODEL = 'res.partner'
    FIELDS_TO_SYNC = [
        'id', 'name', 'display_name', 'write_date', 'company_type', 'street', 'city',
        'zip', 'country_id', 'phone', 'email', 'website', 'vat'
    ]

    def __init__(self, source_conn, dest_conn, key_manager, last_sync_time, loggers=None):
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        self.last_sync_time = last_sync_time
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_partner_sync_id']

        self.logger = loggers.get("contacts_sync", logging.getLogger(__name__))
        self.activity_logger = loggers.get("activity", logging.getLogger(__name__))
        self.error_logger = loggers.get("error", logging.getLogger(__name__))

        self.logger.info("تم تهيئة وحدة مزامنة جهات الاتصال.")

    def run(self):
        self.logger.info("بدء مزامنة جهات الاتصال...")
        
        domain = [('write_date', '>', self.last_sync_time)]
        source_ids = self.source[self.MODEL].search(domain)
        source_data = self.source[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        self.logger.info(f"تم العثور على {total_records} سجل في المصدر.")

        records_to_create = []
        records_to_update = []

        for i, record in enumerate(source_data):
            self.logger.debug(f"  - معالجة سجل {i+1}/{total_records}: {record.get('display_name', '')} (ID: {record['id']})")
            
            source_id = record['id']
            transformed_data = self._transform_data(record)

            search_domain = [('x_partner_sync_id', '=', str(source_id))]
            existing_record_ids = self.dest[self.MODEL].search(search_domain, limit=1)
            
            if existing_record_ids:
                destination_id = existing_record_ids[0]
                records_to_update.append({
                    'id': destination_id,
                    'data': transformed_data,
                    'source_id': source_id
                })
            else:
                transformed_data['x_partner_sync_id'] = str(source_id)
                records_to_create.append(transformed_data)

        if records_to_create:
            self._batch_create_records(records_to_create)

        if records_to_update:
            self._batch_update_records(records_to_update)
            
        self._handle_deletions()

        self.logger.info("اكتملت مزامنة جهات الاتصال.")

    def _handle_deletions(self):
        """
        يتعامل مع حذف السجلات عن طريق أرشفة السجلات في الوجهة
        التي لم تعد موجودة في المصدر.
        """
        self.logger.info("بدء معالجة حذف جهات الاتصال...")
        
        # 1. جلب جميع معرفات المصدر المخزنة محليًا لـ res.partner.
        mapped_source_ids = self.key_manager.get_all_source_ids_for_model(self.MODEL)
        self.logger.debug(f"  - تم العثور على {len(mapped_source_ids)} معرف مصدر mapped لـ {self.MODEL}.")

        if not mapped_source_ids:
            self.logger.info("  - لا توجد معرفات مصدر mapped لـ res.partner. تخطي معالجة الحذف.")
            return

        # 2. جلب جميع معرفات res.partner النشطة من نظام المصدر.
        active_source_ids = self.source[self.MODEL].search([])
        self.logger.debug(f"  - تم العثور على {len(active_source_ids)} معرف res.partner نشط في المصدر.")

        # 3. تحديد السجلات التي تم حذفها في المصدر (موجودة في mapped_source_ids ولكن ليست في active_source_ids).
        deleted_source_ids = [sid for sid in mapped_source_ids if sid not in active_source_ids]
        self.logger.info(f"  - تم تحديد {len(deleted_source_ids)} سجل res.partner للحذف (الأرشفة) في الوجهة.")

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
                    self.activity_logger.info(f"    - تم أرشفة جهة الاتصال ID: {destination_id} في الوجهة وإزالة الربط للمصدر ID: {source_id}.")
                except Exception as e:
                    self.error_logger.error(f"    - [خطأ] فشل في أرشفة جهة الاتصال ID {destination_id} (المصدر ID: {source_id}). الخطأ: {e}")
            else:
                self.logger.warning(f"    - تحذير: لم يتم العثور على معرف الوجهة لـ res.partner المصدر ID: {source_id} في قاعدة بيانات الربط.")

        self.logger.info("اكتملت معالجة حذف جهات الاتصال.")

    def _batch_create_records(self, records_data):
        self.logger.info(f"    - إنشاء {len(records_data)} سجل جديد دفعة واحدة.")
        try:
            new_destination_ids = self.dest[self.MODEL].create(records_data)
            for i, new_id in enumerate(new_destination_ids):
                source_id = records_data[i]['x_partner_sync_id'] # Assuming x_partner_sync_id is set in transformed_data
                self.key_manager.add_mapping(self.MODEL, int(source_id), new_id)
                self.logger.debug(f"      - تم إنشاء سجل جديد في الوجهة بمعرف ID: {new_id} وتم تسجيل الربط للمصدر ID: {source_id}.")
        except Exception as e:
            self.error_logger.error(f"    - [خطأ] فشل في إنشاء سجلات دفعة واحدة: {e}")

    def _batch_update_records(self, records_to_update):
        self.logger.info(f"    - تحديث {len(records_to_update)} سجل دفعة واحدة.")
        try:
            for record_data in records_to_update:
                destination_id = record_data['id']
                source_id = record_data['source_id']
                data = record_data['data']
                self.dest[self.MODEL].write([destination_id], data)
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                self.logger.debug(f"      - تم تحديث سجل الوجهة ID: {destination_id} وتم تسجيل الربط للمصدر ID: {source_id}.")
        except Exception as e:
            self.error_logger.error(f"    - [خطأ] فشل في تحديث سجلات دفعة واحدة: {e}")

    def _transform_data(self, source_record):
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)
        data_to_sync.pop('write_date', None)
        data_to_sync.pop('display_name', None)

        if data_to_sync.get('country_id'):
            country_name = data_to_sync['country_id'][1]
            dest_country_ids = self.dest['res.country'].search([('name', '=', country_name)], limit=1)
            if dest_country_ids:
                data_to_sync['country_id'] = dest_country_ids[0]
            else:
                data_to_sync.pop('country_id')
                self.logger.warning(f"    - تحذير: لم يتم العثور على بلد '{country_name}' في نظام الوجهة. سيتم تجاهل الحقل.")
        
        return data_to_sync