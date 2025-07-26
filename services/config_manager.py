# -*- coding: utf-8 -*-
"""
المرحلة 1: وحدة الإعدادات والاتصال
config_manager.py

الغرض:
- قراءة بيانات الاتصال لكلا نظامي Odoo (Community و Online) من ملف .ini خارجي.
- توفير طريقة سهلة للوصول إلى هذه الإعدادات من أي مكان في التطبيق.

المكتبات المستخدمة:
- configparser: مكتبة بايثون أساسية لقراءة ملفات الإعدادات.
"""

import configparser
import os

class ConfigManager:
    """
    كلاس لإدارة وقراءة الإعدادات من ملف config.ini.
    يتأكد من وجود الملف ويقوم بتحميل الأقسام المختلفة.
    """
    def __init__(self, config_file='config.ini'):
        """
        تهيئة مدير الإعدادات وتحميل البيانات عند إنشاء الكائن.
        
        Args:
            config_file (str): مسار ملف الإعدادات (الافتراضي هو 'config.ini').
        Raises:
            FileNotFoundError: إذا لم يتم العثور على ملف الإعدادات.
        """
        # التحقق مما إذا كان ملف الإعدادات موجودًا قبل محاولة قراءته.
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"ملف الإعدادات '{config_file}' غير موجود. يرجى إنشاء الملف أولاً.")
            
        self.config = configparser.ConfigParser()
        # قراءة ملف الإعدادات وتحميل الأقسام والقيم.
        self.config.read(config_file)
        print(f"تم تحميل الإعدادات بنجاح من '{config_file}'.")

    def get_community_credentials(self):
        """
        جلب بيانات اعتماد Odoo Community (نظام المصدر).
        
        Returns:
            dict: قاموس يحتوي على بيانات الاعتماد (host, port, database, username, password).
        Raises:
            ValueError: إذا كان قسم [odoo_community] مفقودًا أو غير مكتمل.
        """
        try:
            # تحويل قسم الإعدادات إلى قاموس.
            return dict(self.config['odoo_community'])
        except KeyError:
            raise ValueError("Section 'COMMUNITY_ODOO' not found or incomplete in config.ini")

    def get_online_credentials(self):
        """
        جلب بيانات اعتماد Odoo Online (نظام الوجهة).

        Returns:
            dict: قاموس يحتوي على بيانات الاعتماد (host, port, database, username, password).
        Raises:
            ValueError: إذا كان قسم [odoo_online] مفقودًا أو غير مكتمل.
        """
        try:
            # تحويل قسم الإعدادات إلى قاموس.
            return dict(self.config['odoo_online'])
        except KeyError:
            raise ValueError("Section 'ONLINE_ODOO' not found or incomplete in config.ini")

# --- مثال على كيفية الاستخدام (للاختبار فقط) ---
# يتم تشغيل هذا الجزء فقط إذا تم تشغيل الملف مباشرة (وليس عند استيراده كوحدة).
if __name__ == '__main__':
    try:
        # إنشاء كائن من مدير الإعدادات لتحميل config.ini.
        config = ConfigManager()

        # جلب بيانات الاعتماد لكلا النظامين.
        community_creds = config.get_community_credentials()
        online_creds = config.get_online_credentials()

        # طباعة البيانات للتأكد من أنها تعمل بشكل صحيح.
        print("\nOdoo Community Credentials:")
        print(community_creds)

        print("\nOdoo Online Credentials:")
        print(online_creds)

    except (FileNotFoundError, ValueError) as e:
        # معالجة الأخطاء المحتملة أثناء قراءة الإعدادات أو جلب بيانات الاعتماد.
        print(f"خطأ: {e}")