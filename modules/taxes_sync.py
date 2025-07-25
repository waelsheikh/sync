# -*- coding: utf-8 -*-
"""
المرحلة 8: وحدة مزامنة الضرائب
modules/taxes_sync.py

الغرض:
- مزامنة سجلات الضرائب (account.tax) من المصدر إلى الوجهة.
- هذه الوحدة ضرورية لضمان مزامنة الضرائب بشكل صحيح قبل الفواتير.
"""

class TaxSyncModule:
    """
    وحدة متخصصة لمزامنة سجلات الضرائب (account.tax).
    """
    MODEL = 'account.tax'
    # الحقول الأساسية للضريبة. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'amount', 'type_tax_use', 'company_id', 'active'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_tax_sync_id']
        print("تم تهيئة وحدة مزامنة الضرائب.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة الضرائب...")
        
        # 1. جلب جميع الشركات من المصدر.
        source_companies = self.source['res.company'].search_read([], ['id', 'name'])
        
        if not source_companies:
            print("  - لا توجد شركات في المصدر لمزامنة الضرائب.")
            return

        total_companies = len(source_companies)
        for i, company in enumerate(source_companies):
            print(f"\n--- مزامنة الضرائب للشركة: {company.get('name')} (ID: {company['id']}) ({i+1}/{total_companies}) ---")
            
            # جلب معرف الشركة المقابل في الوجهة باستخدام `x_company_sync_id`.
            dest_company_ids_in_dest = self.dest['res.company'].search([('x_company_sync_id', '=', str(company['id']))], limit=1)
            if not dest_company_ids_in_dest:
                print(f"  - تحذير: لم يتم العثور على الشركة ID {company['id']} في الوجهة عبر x_company_sync_id. سيتم تخطي ضرائب هذه الشركة.")
                continue
            dest_company_id = dest_company_ids_in_dest[0]

            # البحث عن الضرائب الخاصة بهذه الشركة في المصدر.
            # استخدام `write_date` للمزامنة التزايدية.
            company_taxes_ids = self.source['account.tax'].search([
                ('company_id', '=', company['id']),
                ('write_date', '>', self.last_sync_time)
            ])
            company_taxes_data = self.source['account.tax'].read(company_taxes_ids, self.FIELDS_TO_SYNC)
            
            total_taxes_in_company = len(company_taxes_data)
            print(f"  - تم العثور على {total_taxes_in_company} ضريبة في المصدر لهذه الشركة.")

            for j, tax_record in enumerate(company_taxes_data):
                print(f"    - معالجة ضريبة {j+1}/{total_taxes_in_company}: {tax_record.get('name')} (ID: {tax_record['id']})")
                self._sync_record(tax_record, dest_company_id)
            
        print("اكتملت مزامنة الضرائب.")

    def _sync_record(self, source_record, dest_company_id):
        """
        مزامنة سجل ضريبة فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_tax_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        """
        source_id = source_record['id']
        source_name = source_record.get('name')
        source_type_tax_use = source_record.get('type_tax_use')

        transformed_data = self._transform_data(source_record, dest_company_id)

        # 1. البحث في الوجهة مباشرة باستخدام `x_tax_sync_id`.
        search_domain_x_sync_id = [('x_tax_sync_id', '=', str(source_id))]
        existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_by_x_sync_id:
            # وجدناه عبر `x_tax_sync_id`، قم بتحديثه.
            destination_id = existing_record_by_x_sync_id[0]
            try:
                self.dest[self.MODEL].write([destination_id], transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                print(f"    - تحديث ضريبة موجودة عبر x_tax_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            except Exception as e:
                print(f"    - [خطأ فادح] فشل في تحديث الضريبة ID {source_id} (عبر x_tax_sync_id). الخطأ: {e}")
        else:
            # 2. إذا لم يتم العثور عليه عبر `x_tax_sync_id`، حاول البحث بالاسم والنوع والشركة.
            search_domain_by_name = [
                ('name', '=', source_name),
                ('type_tax_use', '=', source_type_tax_use),
                ('company_id', '=', dest_company_id)
            ]
            existing_record_by_name = self.dest[self.MODEL].search(search_domain_by_name, limit=1)

            if existing_record_by_name:
                # وجدناه عبر الاسم والنوع والشركة، قم بالتحديث وتعيين `x_tax_sync_id`.
                destination_id = existing_record_by_name[0]
                print(f"    - تحديث ضريبة موجودة عبر الاسم والنوع والشركة. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
                try:
                    self.dest[self.MODEL].write([destination_id], transformed_data)
                    # تعيين `x_tax_sync_id` لهذا السجل إذا تم العثور عليه بالاسم.
                    self.dest[self.MODEL].write([destination_id], {'x_tax_sync_id': str(source_id)}) 
                    # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                    self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                    print(f"    - تحديث ضريبة موجودة عبر الاسم والنوع والشركة. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
                except Exception as e:
                    print(f"    - [خطأ فادح] فشل في تحديث الضريبة ID {source_id} (عبر الاسم والنوع والشركة). الخطأ: {e}")
            else:
                # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                transformed_data['x_tax_sync_id'] = str(source_id) # تأكد من تعيين `x_tax_sync_id` للسجلات الجديدة.
                print(f"    - إنشاء ضريبة جديدة للمصدر ID: {source_id} تحت الشركة ID: {dest_company_id}")
                try:
                    new_destination_id = self.dest[self.MODEL].create(transformed_data)
                    # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                    self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                    print(f"    - تم إنشاء ضريبة جديدة في الوجهة بمعرف ID: {new_destination_id}.")
                except Exception as e:
                    print(f"    - [خطأ فادح] فشل في إنشاء الضريبة ID {source_id}. الخطأ: {e}")

    def _transform_data(self, source_record, dest_company_id):
        """
        تحويل بيانات الضريبة من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)
        data_to_sync['company_id'] = dest_company_id
        return data_to_sync
