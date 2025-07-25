# -*- coding: utf-8 -*-
"""
المرحلة 7: وحدة مزامنة شجرة الحسابات
modules/accounts_sync.py

الغرض:
- مزامنة شجرة الحسابات (account.account) من المصدر إلى الوجهة.
- هذه الوحدة بسيطة نسبيًا لأن الحسابات لا تحتوي على علاقات معقدة كثيرة.
"""

class AccountSyncModule:
    """
    وحدة متخصصة لمزامنة شجرة الحسابات (account.account).
    """
    MODEL = 'account.account'
    # الحقول الأساسية للحساب. تأكد من تطابقها مع احتياجاتك.
    FIELDS_TO_SYNC = [
        'id', 'name', 'code', 'reconcile', 'company_ids', 'account_type', 'write_date'
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
        self.dest_fields = self.FIELDS_TO_SYNC + ['x_account_sync_id']
        print("تم تهيئة وحدة مزامنة شجرة الحسابات.")

    def run(self):
        """
        نقطة الدخول الرئيسية لتشغيل مزامنة هذه الوحدة.
        تقوم بجلب السجلات المعدلة من المصدر وتمريرها لدالة المزامنة الفردية.
        """
        print("بدء مزامنة شجرة الحسابات...")
        
        # 1. جلب جميع الشركات من المصدر.
        source_companies = self.source['res.company'].search_read([], ['id', 'name'])
        
        if not source_companies:
            print("  - لا توجد شركات في المصدر لمزامنة الحسابات.")
            return

        total_companies = len(source_companies)
        for i, company in enumerate(source_companies):
            print(f"\n--- مزامنة الحسابات للشركة: {company.get('name')} (ID: {company['id']}) ({i+1}/{total_companies}) ---")
            
            # جلب معرف الشركة المقابل في الوجهة باستخدام `x_company_sync_id`.
            dest_company_ids_in_dest = self.dest['res.company'].search([('x_company_sync_id', '=', str(company['id']))], limit=1)
            if not dest_company_ids_in_dest:
                print(f"  - تحذير: لم يتم العثور على الشركة ID {company['id']} في الوجهة عبر x_company_sync_id. سيتم تخطي حسابات هذه الشركة.")
                continue
            dest_company_id = dest_company_ids_in_dest[0]

            # البحث عن الحسابات الخاصة بهذه الشركة في المصدر.
            # استخدام `write_date` للمزامنة التزايدية.
            company_accounts_ids = self.source['account.account'].search([
                ('company_ids', 'in', [company['id']]),
                ('write_date', '>', self.last_sync_time)
            ])
            company_accounts_data = self.source['account.account'].read(company_accounts_ids, self.FIELDS_TO_SYNC)
            
            total_accounts_in_company = len(company_accounts_data)
            print(f"  - تم العثور على {total_accounts_in_company} حساب في المصدر لهذه الشركة.")

            for j, account_record in enumerate(company_accounts_data):
                print(f"    - معالجة حساب {j+1}/{total_accounts_in_company}: {account_record.get('code')} {account_record.get('name')} (ID: {account_record['id']})")
                self._sync_record(account_record, dest_company_id)
            
        print("اكتملت مزامنة شجرة الحسابات.")

    def _sync_record(self, source_record, dest_company_id):
        """
        مزامنة سجل حساب فردي.
        يقرر ما إذا كان يجب إنشاء سجل جديد أو تحديث سجل موجود بناءً على `x_account_sync_id`.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        """
        source_id = source_record['id']
        source_code = source_record.get('code')
        source_name = source_record.get('name')

        # لا نبحث عن الحسابات التي ليس لها كود لأنها غير موثوقة.
        if not source_code:
            print(f"    - تخطي الحساب '{source_name}' (ID: {source_id}) لأنه لا يحتوي على كود في المصدر.")
            return

        transformed_data = self._transform_data(source_record, dest_company_id)
        # تعيين `company_ids` بشكل صريح لربط الحساب بالشركة الصحيحة في الوجهة.
        transformed_data['company_ids'] = [(6, 0, [dest_company_id])]

        # 1. البحث في الوجهة مباشرة باستخدام `x_account_sync_id`.
        search_domain_x_sync_id = [('x_account_sync_id', '=', str(source_id))]
        existing_record_by_x_sync_id = self.dest[self.MODEL].search(search_domain_x_sync_id, limit=1)

        if existing_record_by_x_sync_id:
            # وجدناه عبر `x_account_sync_id`، قم بتحديثه.
            destination_id = existing_record_by_x_sync_id[0]
            print(f"    - تحديث حساب موجود عبر x_account_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            try:
                self.dest[self.MODEL].write([destination_id], transformed_data)
                # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                print(f"    - تحديث حساب موجود عبر x_account_sync_id. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
            except Exception as e:
                print(f"    - [خطأ فادح] فشل في تحديث الحساب ID {source_id} (عبر x_account_sync_id). الخطأ: {e}")
        else:
            # 2. إذا لم يتم العثور عليه عبر `x_account_sync_id`، حاول البحث بالكود ومعرف الشركة.
            search_domain_by_code = [
                ('code', '=', source_code),
                ('company_ids', 'in', [dest_company_id])
            ]
            existing_record_by_code = self.dest[self.MODEL].search(search_domain_by_code, limit=1)

            if existing_record_by_code:
                # وجدناه عبر الكود ومعرف الشركة، قم بالتحديث وتعيين `x_account_sync_id`.
                destination_id = existing_record_by_code[0]
                print(f"    - تحديث حساب موجود عبر الكود. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
                try:
                    self.dest[self.MODEL].write([destination_id], transformed_data)
                    # تعيين `x_account_sync_id` لهذا السجل إذا تم العثور عليه بالاسم.
                    self.dest[self.MODEL].write([destination_id], {'x_account_sync_id': str(source_id)}) 
                    # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد التحديث.
                    self.key_manager.add_mapping(self.MODEL, source_id, destination_id)
                    print(f"    - تحديث حساب موجود عبر الكود. المصدر ID: {source_id} -> الوجهة ID: {destination_id}")
                except Exception as e:
                    print(f"    - [خطأ فادح] فشل في تحديث الحساب ID {source_id} (عبر الكود). الخطأ: {e}")
            else:
                # 3. لم يتم العثور عليه بأي من الطريقتين، قم بإنشاء جديد.
                transformed_data['x_account_sync_id'] = str(source_id) # تأكد من تعيين `x_account_sync_id` للسجلات الجديدة.
                print(f"    - إنشاء حساب جديد للمصدر ID: {source_id} تحت الشركة ID: {dest_company_id}")
                try:
                    new_destination_id = self.dest[self.MODEL].create(transformed_data)
                    # تسجيل الربط في قاعدة البيانات المحلية (sync_map.db) بعد الإنشاء.
                    self.key_manager.add_mapping(self.MODEL, source_id, new_destination_id)
                    print(f"    - تم إنشاء حساب جديد في الوجهة بمعرف ID: {new_destination_id}.")
                except Exception as e:
                    print(f"    - [خطأ فادح] فشل في إنشاء الحساب ID {source_id}. الخطأ: {e}")

    def _transform_data(self, source_record, dest_company_id):
        """
        تحويل بيانات الحساب من تنسيق المصدر إلى تنسيق مناسب لـ Odoo API في الوجهة.

        Args:
            source_record (dict): قاموس يمثل بيانات السجل من نظام المصدر.
            dest_company_id (int): معرف الشركة المقابل في نظام الوجهة.
        Returns:
            dict: قاموس يمثل البيانات المحولة الجاهزة للإرسال إلى Odoo الوجهة.
        """
        data_to_sync = source_record.copy()
        data_to_sync.pop('id', None)

        # معالجة نوع الحساب (نقل مباشر للقيمة).
        # اسم الحقل في الإصدارات الحديثة هو 'account_type'.
        if source_record.get('account_type'):
            data_to_sync['account_type'] = source_record['account_type']
        
        # التأكد من وجود الكود دائمًا.
        print(f"          - Code before transformation: {data_to_sync.get('code')}")
        if not data_to_sync.get('code'):
            data_to_sync['code'] = f"SYNC_{source_record['id']}"
        print(f"          - Code after transformation: {data_to_sync['code']}")

        # إزالة `company_ids` من سجل المصدر إذا كان موجودًا، حيث سيتم تعيينه بشكل صريح في `_sync_record`.
        data_to_sync.pop('company_ids', None)
        # إزالة `company_id` بشكل صريح في حال وجوده.
        data_to_sync.pop('company_id', None)

        return data_to_sync