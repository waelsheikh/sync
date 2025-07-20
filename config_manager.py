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
    """
    def __init__(self, config_file='config.ini'):
        """
        تهيئة مدير الإعدادات وتحميل البيانات عند إنشاء الكائن.

        Args:
            config_file (str): مسار ملف الإعدادات.
        """
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"ملف الإعدادات '{config_file}' غير موجود. يرجى إنشاء الملف أولاً.")
            
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        print(f"تم تحميل الإعدادات بنجاح من '{config_file}'.")

    def get_community_credentials(self):
        """
        جلب بيانات اعتماد Odoo Community.

        Returns:
            dict: قاموس يحتوي على (url, db, username, password).
        """
        try:
            return dict(self.config['odoo_community'])
        except KeyError:
            raise ValueError("قسم [odoo_community] غير موجود أو غير مكتمل في ملف الإعدادات.")

    def get_online_credentials(self):
        """
        جلب بيانات اعتماد Odoo Online.

        Returns:
            dict: قاموس يحتوي على (url, db, username, password).
        """
        try:
            return dict(self.config['odoo_online'])
        except KeyError:
            raise ValueError("قسم [odoo_online] غير موجود أو غير مكتمل في ملف الإعدادات.")

# --- مثال على كيفية الاستخدام (للاختبار فقط) ---
if __name__ == '__main__':
    try:
        # إنشاء كائن من مدير الإعدادات
        config = ConfigManager()

        # جلب بيانات الاعتماد
        community_creds = config.get_community_credentials()
        online_creds = config.get_online_credentials()

        # طباعة البيانات للتأكد من أنها تعمل
        print("\nOdoo Community Credentials:")
        print(community_creds)

        print("\nOdoo Online Credentials:")
        print(online_creds)

    except (FileNotFoundError, ValueError) as e:
        print(f"خطأ: {e}")