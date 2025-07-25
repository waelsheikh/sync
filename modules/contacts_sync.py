# -*- coding: utf-8 -*-
"""
المرحلة 5: وحدة مزامنة جهات الاتصال
modules/contacts_sync.py

الغرض:
- مزامنة بيانات جهات الاتصال (res.partner) من نظام المصدر إلى نظام الوجهة.
- التعامل مع إنشاء جهات اتصال جديدة وتحديث الموجودة.
- استخدام الخدمات المقدمة من SyncEngine (الاتصالات ومدير المفاتيح).
"""

class ContactSyncModule:
    """
    وحدة متخصصة لمزامنة جهات الاتصال (res.partner).
    """
    MODEL = 'res.partner'
    # قائمة الحقول التي نريد مزامنتها. يمكن تعديلها حسب الحاجة.
    # 'id' ضروري دائمًا. 'write_date' مهم لتتبع التغييرات.
    FIELDS_TO_SYNC = [
        'id', 'name', 'display_name', 'write_date', 'company_type', 'street', 'city',
        'zip', 'country_id', 'phone', 'email', 'website', 'vat'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_partner_sync_id']

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة جهات الاتصال...")
        
        # 1. استخراج البيانات من المصدر.
        # جلب فقط السجلات التي تم تعديلها منذ آخر مزامنة (باستخدام write_date).
        domain = [('write_date', '>', self.last_sync_time)]
        source_ids = self.source[self.MODEL].search(domain)
        source_data = self.source[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} سجل في المصدر.")

        # 2. المرور على كل سجل ومزامنته.
        for i, record in enumerate(source_data):
            print(f"  - معالجة سجل {i+1}/{total_records}: {record.get('display_name', '')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة جهات الاتصال.")

    def _sync_record(self, source_record):
        """
        مزامنة سجل فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_partner_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        """
        source_id = source_record['id']
        
        # تحويل البيانات لتكون متوافقة مع Odoo API.
        transformed_data = self._transform_data(source_record)

        # البحث في الوجهة مباشرة باستخدام حقل `x_partner_sync_id`.
        # هذا يضمن أننا نعتمد على المعرف الفريد المخزن في Odoo الوجهة نفسه.
        search_domain = [('x_partner_sync_id', '=', str(source_id))]
        existing_record_ids = self.dest[self.MODEL].search(search_domain, limit=1)
        
        if existing_record_ids:
            # تحديث (Update): السجل موجود بالفعل في الوجهة.
            destination_id = existing_record_ids[0]
            print(f"    - تحديث سجل موجود عبر x_partner_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            self.dest[self.MODEL].write([destination_id], transformed_data)
            # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
            self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
        else:
            # إنشاء (Create): السجل غير موجود في الوجهة.
            # إضافة معرف المصدر إلى الحقل المخصص `x_partner_sync_id` في الوجهة.
            transformed_data['x_partner_sync_id'] = str(source_id)
            
            print(f"    - إنشاء سجل جديد للمصدر ID: {source_id}")
            new_destination_id = self.dest[self.MODEL].create(transformed_data)
            
            # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
            self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
            print(f"    - تم إنشاء سجل جديد في الوجهة بمعرف ID: {new_destination_id} وتم تسجيل الربط.")

    def _transform_data(self, source_record):
        """
        تحويل البيانات من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.
        يتضمن معالجة العلاقات (مثل country_id).

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        # إنشاء نسخة من السجل لتجنب تعديل القاموس الأصلي.
        data_to_sync = source_record.copy()
        
        # إزالة الحقول التي لا نريد إرسالها إلى الوجهة (مثل ID المصدر وتاريخ التعديل).
        data_to_sync.pop('id', None)
        data_to_sync.pop('write_date', None)
        data_to_sync.pop('display_name', None)

        # مثال على معالجة علاقة Many2One: country_id.
        # حقل country_id في المصدر يأتي كـ [id, name]، نحتاج فقط إلى الاسم للبحث عنه في الوجهة.
        if data_to_sync.get('country_id'):
            country_name = data_to_sync['country_id'][1]
            # البحث عن معرف البلد في نظام الوجهة باستخدام الاسم.
            dest_country_ids = self.dest['res.country'].search([('name', '=', country_name)], limit=1)
            if dest_country_ids:
                data_to_sync['country_id'] = dest_country_ids[0]
            else:
                # إذا لم يتم العثور على البلد، قم بإزالته لتجنب خطأ أثناء الإنشاء/التحديث.
                data_to_sync.pop('country_id')
                print(f"    - تحذير: لم يتم العثور على بلد '{country_name}' في نظام الوجهة. سيتم تجاهل الحقل.")
        
        return data_to_sync