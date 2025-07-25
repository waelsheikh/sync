# -*- coding: utf-8 -*-
"""
المرحلة 6: وحدة مزامنة الشركات
modules/company_sync.py

الغرض:
- مزامنة بيانات الشركات (res.company) من نظام المصدر إلى نظام الوجهة.
- هذه الوحدة حاسمة لأن العديد من السجلات الأخرى (مثل الحسابات ودفاتر اليومية) تعتمد على company_id.
"""

class CompanySyncModule:
    """
    وحدة متخصصة لمزامنة الشركات (res.company).
    """
    MODEL = 'res.company'
    # قائمة الحقول التي نريد مزامنتها. يمكن تعديلها حسب الحاجة.
    FIELDS_TO_SYNC = [
        'id', 'name', 'currency_id', 'phone', 'email', 'website', 'vat', 'company_registry'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_company_sync_id']
        print("تم تهيئة وحدة مزامنة الشركات.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة الشركات...")
        
        # 1. استخراج البيانات من المصدر.
        # بالنسبة للشركات، نقوم دائمًا بجلب جميع السجلات لضمان وجودها في ذاكرة الربط.
        source_ids = self.source[self.MODEL].search([])
        source_data = self.source[self.MODEL].read(source_ids, self.FIELDS_TO_SYNC)
        
        total_records = len(source_data)
        print(f"تم العثور على {total_records} شركة في المصدر.")

        # 2. المرور على كل سجل ومزامنته.
        for i, record in enumerate(source_data):
            print(f"  - معالجة شركة {i+1}/{total_records}: {record.get('name')} (ID: {record['id']})")
            self._sync_record(record)
            
        print("اكتملت مزامنة الشركات.")

    def _sync_record(self, source_record):
        """
        مزامنة سجل شركة فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_company_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        """
        source_id = source_record['id']
        company_name = source_record.get('name')

        transformed_data = self._transform_data(source_record)

        # 1. البحث في الوجهة مباشرة باستخدام حقل `x_company_sync_id`.
        # هذا يضمن أننا نعتمد على المعرف الفريد المخزن في Odoo الوجهة نفسه.
        search_domain_x_sync_id = [('x_company_sync_id', '=', str(source_id))]
        existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_by_x_sync_id:
            # وجدناه عبر x_company_sync_id، قم بتحديثه.
            destination_id = existing_record_by_x_sync_id[0]
            print(f"    - تحديث شركة موجودة عبر x_company_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            self.dest[self.MODEL].write([destination_id], transformed_data)
            # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
            self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
        else:
            # 2. إذا لم يتم العثور عليه عبر x_company_sync_id، حاول البحث بالاسم في Odoo الوجهة.
            existing_dest_company_ids_by_name = self.dest[self.MODEL].search([('name', '=', company_name)], limit=1)
            if existing_dest_company_ids_by_name:
                # وجدناه بالاسم، قم بتحديثه وتعيين `x_company_sync_id`.
                destination_id = existing_dest_company_ids_by_name[0]
                print(f"    - الشركة موجودة بالفعل في الوجهة بالاسم '{company_name}'. سيتم تحديثها. ID: {destination_id}")
                self.dest[self.MODEL].write([destination_id], transformed_data)
                # تعيين `x_company_sync_id` لهذا السجل إذا تم العثور عليه بالاسم.
                self.dest[self.MODEL].write([destination_id], {'x_company_sync_id': str(source_id)})
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
            else:
                # 3. إذا لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء شركة جديدة.
                transformed_data['x_company_sync_id'] = str(source_id) # تأكد من تعيين `x_company_sync_id` للسجلات الجديدة.
                print(f"    - إنشاء شركة جديدة للمصدر ID: {source_id}")
                new_destination_id = self.dest[self.MODEL].create(transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                print(f"    - تم إنشاء شركة جديدة في الوجهة بمعرف ID: {new_destination_id}.")

    def _transform_data(self, source_record):
        """
        تحويل بيانات الشركة من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # معالجة currency_id (ربط العملة).
        # نفترض أن معرفات العملات متناسقة أو يمكن ربطها مباشرة.
        # في سيناريو أكثر تعقيدًا، قد تحتاج إلى وحدة مزامنة للعملات.
        if data_to_sync.get('currency_id'):
            source_currency_id = data_to_sync['currency_id'][0]
            data_to_sync['currency_id'] = source_currency_id
            
        return data_to_sync