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

import odoorpc

from odoorpc.exceptions import Error as OdooError

class OdooConnector:
    """
    كلاس لإنشاء وإدارة اتصال بخادم Odoo محدد.
    """
    def __init__(self, credentials):
        """
        تهيئة الاتصال باستخدام بيانات الاعتماد المقدمة.

        Args:
            credentials (dict): قاموس يحتوي على (url, db, username, password).
        """
        self.url = credentials.get('url')
        self.db = credentials.get('db')
        self.username = credentials.get('username')
        self.password = credentials.get('password')
        self.api = None
        self._connect()

    def _connect(self):
        """
        إنشاء اتصال فعلي بخادم Odoo وتسجيل الدخول.
        """
        try:
            # تجهيز كائن الاتصال
            # يتم تحديد البروتوكول 'jsonrpc+ssl' إذا كان الرابط يبدأ بـ https
            protocol = 'jsonrpc+ssl' if self.url.startswith('https') else 'jsonrpc'
            port = 443 if protocol == 'jsonrpc+ssl' else 8069
            
            # استخلاص اسم المضيف من الرابط
            host = self.url.replace('https://', '').replace('http://', '')

            self.api = odoorpc.ODOO(host, protocol=protocol, port=port)
            
            # تسجيل الدخول إلى قاعدة البيانات
            self.api.login(self.db, self.username, self.password)
            
            print(f"تم الاتصال وتسجيل الدخول بنجاح إلى Odoo في '{self.url}' (قاعدة البيانات: {self.db})")

        except OdooError as e:
            print(f"خطأ في تسجيل الدخول إلى Odoo: {e}")
            print("الرجاء التحقق من بيانات الاعتماد (URL, DB, Username, Password) في ملف config.ini")
            raise ConnectionError(f"فشل الاتصال بـ Odoo: {e}") from e
        except Exception as e:
            print(f"حدث خطأ غير متوقع أثناء الاتصال بـ Odoo: {e}")
            raise

    def get_api(self):
        """
        إرجاع كائن الـ API الجاهز للاستخدام.

        Returns:
            odoorpc.ODOO: كائن Odoo API.
        """
        if not self.api or not self.api.logged_in:
            print("الاتصال غير قائم. محاولة إعادة الاتصال...")
            self._connect()
        return self.api

# --- مثال على كيفية الاستخدام (للاختبار فقط) ---
if __name__ == '__main__':
    # هذا المثال يعتمد على وجود الملفات من المراحل السابقة
    from config_manager import ConfigManager

    try:
        # 1. تحميل الإعدادات
        config = ConfigManager()
        community_creds = config.get_community_credentials()
        online_creds = config.get_online_credentials()

        # 2. إنشاء اتصال بـ Odoo Community
        print("\n--- محاولة الاتصال بـ Odoo Community ---")
        community_connector = OdooConnector(community_creds)
        community_api = community_connector.get_api()

        # 3. تنفيذ أمر بسيط (جلب عدد جهات الاتصال كاختبار)
        if community_api:
            Partner = community_api.env['res.partner']
            partner_count = Partner.search_count([])
            print(f"نجح الاختبار: عدد جهات الاتصال في Community هو {partner_count}")

        # 4. إنشاء اتصال بـ Odoo Online
        print("\n--- محاولة الاتصال بـ Odoo Online ---")
        online_connector = OdooConnector(online_creds)
        online_api = online_connector.get_api()

        # 5. تنفيذ أمر بسيط (جلب إصدار الخادم كاختبار)
        if online_api:
            version = online_api.version
            print(f"نجح الاختبار: إصدار خادم Odoo Online هو {version['server_serie']}")

    except (FileNotFoundError, ValueError, ConnectionError) as e:
        print(f"\nفشل الاختبار. خطأ: {e}")
    except Exception as e:
        print(f"\nفشل الاختبار. حدث خطأ غير متوقع: {e}")
