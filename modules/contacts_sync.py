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
        'zip', 'country_id', 'phone', 'mobile', 'email', 'website', 'vat'
    ]

    def __init__(self, source_conn, dest_conn, key_manager):
        """
        تهيئة الوحدة بالخدمات التي تحتاجها من المحرك.

        Args:
            source_conn: كائن اتصال Odoo API للمصدر.
            dest_conn: كائن اتصال Odoo API للوجهة.
            key_manager: كائن مدير مفاتيح المزامنة.
        """
        self.source = source_conn
        self.dest = dest_conn
        self.key_manager = key_manager
        # إضافة حقل المزامنة المخصص إلى قائمة الحقول المطلوبة في الوجهة
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_sync_id']

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        """
        print("بدء مزامنة جهات الاتصال...")
        
        # 1. استخراج البيانات من المصدر
        # سنقوم بجلب جميع جهات الاتصال في هذا المثال.
        # في بيئة الإنتاج، يجب تحسين هذا لجلب التغييرات فقط.
        source_ids = self.source.env[self.MODEL].search([])
        source_data = self.source.env[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} سجل في المصدر.")

        # 2. المرور على كل سجل ومزامنته
        for i, record in enumerate(source_data):
            print(f"  - معالجة سجل {i+1}/{total_records}: {record.get('display_name', '')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة جهات الاتصال.")

    def _sync_record(self, source_record):
        """
        مزامنة سجل فردي. يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود.
        """
        source_id = source_record['id']
        
        # البحث في الذاكرة المحلية (قاعدة البيانات) لمعرفة ما إذا كان السجل موجودًا بالفعل في الوجهة
        destination_id = self.key_manager.get_destination_id(self.MODEL, source_id)
        
        # تحويل البيانات لتكون متوافقة مع Odoo API
        transformed_data = self._transform_data(source_record)
        
        if destination_id:
            # تحديث (Update): السجل موجود بالفعل في الوجهة
            print(f"    - تحديث سجل موجود. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            self.dest.env[self.MODEL].write([destination_id], transformed_data)
        else:
            # إنشاء (Create): السجل غير موجود في الوجهة
            # إضافة معرف المصدر إلى الحقل المخصص في الوجهة
            transformed_data['x_sync_id'] = f"{self.MODEL},{source_id}"
            
            print(f"    - إنشاء سجل جديد للمصدر ID: {source_id}")
            new_destination_id = self.dest.env[self.MODEL].create(transformed_data)
            
            # تسجيل الربط الجديد في قاعدة البيانات المحلية
            self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
            print(f"    - تم إنشاء سجل جديد في الوجهة بمعرف ID: {new_destination_id} وتم تسجيل الربط.")

    def _transform_data(self, source_record):
        """
        تحويل البيانات ومعالجة العلاقات (مثل country_id).
        """
        # إنشاء نسخة من السجل لتجنب تعديل القاموس الأصلي
        data_to_sync = source_record.copy()
        
        # إزالة الحقول التي لا نريد إرسالها إلى الوجهة
        data_to_sync.pop('id', None)
        data_to_sync.pop('write_date', None)
        data_to_sync.pop('display_name', None)

        # مثال على معالجة علاقة Many2One: country_id
        # country_id في المصدر يأتي كـ [id, name]، نحتاج فقط إلى الاسم للبحث عنه في الوجهة
        if data_to_sync.get('country_id'):
            country_name = data_to_sync['country_id'][1]
            # البحث عن معرف البلد في نظام الوجهة باستخدام الاسم
            dest_country_ids = self.dest.env['res.country'].search([('name', '=', country_name)], limit=1)
            if dest_country_ids:
                data_to_sync['country_id'] = dest_country_ids[0]
            else:
                # إذا لم يتم العثور على البلد، قم بإزالته لتجنب خطأ
                data_to_sync.pop('country_id')
                print(f"    - تحذير: لم يتم العثور على بلد '{country_name}' في نظام الوجهة. سيتم تجاهل الحقل.")
        
        return data_to_sync
