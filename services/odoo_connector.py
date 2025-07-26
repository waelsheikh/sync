# -*- coding: utf-8 -*-
"""
المرحلة 3: وحدة الاتصال بـ Odoo (API Connector)
odoo_connector.py

الغرض:
- تبسيط عملية إنشاء اتصال بخادم Odoo باستخدام بيانات الاعتماد.
- توفير كائن جاهز لتنفيذ الأوامر على Odoo (بحث، قراءة، إنشاء، تحديث).
- معالجة أخطاء الاتصال الأساسية.

المكتبات المستخدمة:
- odoorpc: مكتبة خارجية قوية للاتصال بـ Odoo API.
"""

import logging
import odoorpc
from urllib.parse import urlparse

from odoorpc.exceptions import Error as OdooError

class OdooConnector:
    """
    كلاس لإنشاء وإدارة اتصال بخادم Odoo محدد.
    يتولى مسؤولية الاتصال، تسجيل الدخول، وتوفير واجهة API، بالإضافة إلى
    التحقق من وجود الحقول المخصصة وإنشائها في نظام الوجهة.
    """
    def __init__(self, credentials, logger=None):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        """
        تهيئة الاتصال باستخدام بيانات الاعتماد المقدمة.

        Args:
            credentials (dict): قاموس يحتوي على بيانات الاتصال (host, db, username, password).
        """
        self.url = credentials.get('url')
        self.db = credentials.get('db')
        self.username = credentials.get('username')
        self.password = credentials.get('password')
        self.api = None
        # يتم استدعاء دالة الاتصال عند تهيئة الكائن.
        self._connect()

    def _connect(self):
        """
        إنشاء اتصال فعلي بخادم Odoo وتسجيل الدخول.
        تستخدم مكتبة odoorpc للتعامل مع تفاصيل الاتصال بـ XML-RPC أو JSON-RPC.
        Raises:
            ConnectionError: إذا فشل الاتصال أو تسجيل الدخول إلى Odoo.
            Exception: لأي أخطاء غير متوقعة أخرى.
        """
        try:
            # تحديد البروتوكول (http/https) والمنفذ بناءً على الـ URL.
            # odoorpc يتعامل مع هذه التفاصيل تلقائيًا بناءً على البروتوكول المحدد.
            protocol = 'json-rpcs' if self.url.startswith('https') else 'json-rpc'
            
            # تحليل الـ URL لاستخراج المضيف والمنفذ.
            parsed_url = urlparse(self.url)
            host = parsed_url.hostname
            # تحديد المنفذ الافتراضي إذا لم يكن محددًا في الـ URL.
            port = parsed_url.port if parsed_url.port else (443 if parsed_url.scheme == 'https' else 8069)

            # تهيئة عميل OdooRPC بجميع بيانات الاعتماد.
            self.api = odoorpc.Client(
                host,
                self.db,
                self.username,
                self.password,
                protocol=protocol,
                port=port
            )
            self.logger.info(f"تم الاتصال وتسجيل الدخول بنجاح إلى Odoo في '{self.url}' (قاعدة البيانات: {self.db})")
            self.logger.debug(f"[DEBUG] In _connect: self.api type: {type(self.api)}, self.api.uid: {self.api.uid if self.api else 'N/A'}")

        except OdooError as e:
            # معالجة الأخطاء الخاصة بـ Odoo (مثل بيانات الاعتماد الخاطئة).
            self.logger.error(f"خطأ في تسجيل الدخول إلى Odoo: {e}")
            self.logger.error("الرجاء التحقق من بيانات الاعتماد (URL, DB, Username, Password) في ملف config.ini")
            raise ConnectionError(f"فشل الاتصال بـ Odoo: {e}") from e
        except Exception as e:
            # معالجة أي أخطاء عامة أخرى قد تحدث أثناء الاتصال.
            self.logger.error(f"حدث خطأ غير متوقع أثناء الاتصال بـ Odoo: {e}")
            raise

    def get_api(self):
        """
        إرجاع كائن الـ API الجاهز للاستخدام لإجراء عمليات على Odoo.

        Returns:
            odoorpc.ODOO: كائن Odoo API المتصل.
        """
        # التحقق مما إذا كان الاتصال لا يزال نشطًا، وإعادة الاتصال إذا لزم الأمر.
        if not self.api or self.api.uid is None:
            self.logger.warning("الاتصال غير قائم. محاولة إعادة الاتصال...")
            self._connect()
        return self.api

    def ensure_custom_field(self, model_name, field_name, field_label, field_type='char'):
        """
        تضمن وجود حقل مخصص في نموذج Odoo معين. إذا لم يكن موجودًا، تقوم بإنشائه.
        هذه الدالة مخصصة للاستخدام مع نظام Odoo الوجهة.

        Args:
            model_name (str): الاسم التقني للنموذج (مثال: 'res.partner').
            field_name (str): الاسم التقني للحقل المخصص (مثال: 'x_my_custom_field').
            field_label (str): الاسم المرئي للحقل في واجهة المستخدم.
            field_type (str): نوع بيانات الحقل (مثال: 'char', 'integer', 'datetime').
        Raises:
            Exception: إذا فشل إنشاء الحقل المخصص.
        """
        # الحصول على كائن نموذج ir.model.fields للتعامل مع الحقول في Odoo.
        IrModelFields = self.api['ir.model.fields']
        
        # البحث عن الحقل الحالي للتأكد مما إذا كان موجودًا بالفعل.
        existing_field_ids = IrModelFields.search([
            ('model', '=', model_name),
            ('name', '=', field_name)
        ])

        if not existing_field_ids:
            # إذا لم يتم العثور على الحقل، قم بإنشائه.
            self.logger.info(f"  - الحقل '{field_name}' غير موجود في النموذج '{model_name}'. جاري الإنشاء...")
            try:
                IrModelFields.create({
                    'name': field_name, # الاسم التقني للحقل.
                    'model': model_name, # النموذج الذي ينتمي إليه الحقل.
                    # البحث عن معرف النموذج في Odoo.
                    'model_id': self.api['ir.model'].search([('model', '=', model_name)])[0],
                    'field_description': field_label, # الاسم المرئي للحقل.
                    'ttype': field_type, # نوع بيانات الحقل.
                    'store': True, # هل يتم تخزين قيمة الحقل في قاعدة البيانات؟ (نعم).
                    'index': True, # هل يتم فهرسة الحقل لتحسين أداء البحث؟ (نعم).
                    'required': False, # هل الحقل إلزامي؟ (لا).
                    'readonly': False, # هل الحقل للقراءة فقط؟ (لا، يمكن تعديله برمجيًا).
                })
                self.logger.info(f"  - تم إنشاء الحقل '{field_name}' بنجاح في النموذج '{model_name}'.")
            except Exception as e:
                # معالجة الأخطاء أثناء إنشاء الحقل.
                self.logger.error(f"  - خطأ أثناء إنشاء الحقل '{field_name}' في النموذج '{model_name}': {e}")
                raise # إعادة إطلاق الخطأ لإيقاف العملية إذا كان إنشاء الحقل حرجًا.
        else:
            # إذا كان الحقل موجودًا بالفعل، لا تفعل شيئًا.
            self.logger.info(f"  - الحقل '{field_name}' موجود بالفعل في النموذج '{model_name}'.")

# --- مثال على كيفية الاستخدام (للاختبار فقط) ---
# يتم تشغيل هذا الجزء فقط إذا تم تشغيل الملف مباشرة (وليس عند استيراده كوحدة).
if __name__ == '__main__':
    # هذا المثال يعتمد على وجود ملف config.ini من المراحل السابقة.
    from config_manager import ConfigManager

    try:
        # 1. تحميل الإعدادات من config.ini.
        config = ConfigManager()
        community_creds = config.get_community_credentials()
        online_creds = config.get_online_credentials()

        # 2. إنشاء اتصال بـ Odoo Community (المصدر).
        print("\n--- محاولة الاتصال بـ Odoo Community ---")
        community_connector = OdooConnector(community_creds)
        community_api = community_connector.get_api()

        # 3. تنفيذ أمر بسيط على Odoo Community (جلب عدد جهات الاتال كاختبار).
        if community_api:
            Partner = community_api.env['res.partner']
            partner_count = Partner.search_count([])
            print(f"نجح الاختبار: عدد جهات الاتصال في Community هو {partner_count}")

        # 4. إنشاء اتصال بـ Odoo Online (الوجهة).
        print("\n--- محاولة الاتصال بـ Odoo Online ---")
        online_connector = OdooConnector(online_creds)
        online_api = online_connector.get_api()

        # 5. تنفيذ أمر بسيط على Odoo Online (جلب إصدار الخادم كاختبار).
        if online_api:
            version = online_api.version
            print(f"نجح الاختبار: إصدار خادم Odoo Online هو {version['server_serie']}")

        # 6. مثال على استخدام ensure_custom_field لإنشاء حقل مخصص (للتجربة).
        print("\n--- اختبار إنشاء حقل مخصص ---")
        online_connector.ensure_custom_field('res.partner', 'x_test_field', 'Test Field', 'char')

    except (FileNotFoundError, ValueError, ConnectionError) as e:
        # معالجة الأخطاء المتعلقة بالملفات، القيم، أو الاتصال.
        print(f"\nفشل الاختبار. خطأ: {e}")
    except Exception as e:
        # معالجة أي أخطاء غير متوقعة.
        print(f"\nفشل الاختبار. حدث خطأ غير متوقع: {e}")