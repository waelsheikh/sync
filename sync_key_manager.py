# -*- coding: utf-8 -*-
"""
المرحلة 2: وحدة إدارة مفتاح المزامنة
sync_key_manager.py

الغرض:
- إنشاء وإدارة قاعدة بيانات SQLite محلية لتخزين جدول الربط (mapping).
- ربط معرف السجل في نظام المصدر (Community) بمعرف السجل المقابل له في نظام الوجهة (Online).
- توفير دوال للبحث عن الروابط وإضافتها.

المكتبات المستخدمة:
- sqlite3: مكتبة بايثون أساسية للتعامل مع قواعد بيانات SQLite.
"""

import sqlite3
import os

class SyncKeyManager:
    """
    كلاس لإدارة جدول الربط في قاعدة بيانات SQLite.
    هذا الكلاس يضمن أن كل سجل يتم مزامنته مرة واحدة فقط (للإنشاء).
    """
    def __init__(self, db_file='sync_map.db'):
        """
        تهيئة مدير مفتاح المزامنة. يتصل بقاعدة البيانات وينشئ الجدول إذا لم يكن موجودًا.

        Args:
            db_file (str): اسم ملف قاعدة بيانات SQLite.
        """
        self.db_file = db_file
        self.conn = None
        try:
            # الاتصال بقاعدة البيانات (سيتم إنشاؤها إذا لم تكن موجودة)
            self.conn = sqlite3.connect(self.db_file)
            self._create_table()
            print(f"تم الاتصال بقاعدة بيانات الربط بنجاح: '{self.db_file}'")
        except sqlite3.Error as e:
            print(f"حدث خطأ في قاعدة البيانات: {e}")
            raise

    def _create_table(self):
        """
        إنشاء جدول الربط (mapping) إذا لم يكن موجودًا.
        الجدول يخزن العلاقة بين معرفات المصدر والوجهة.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mapping (
                    source_model TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    destination_id INTEGER NOT NULL,
                    PRIMARY KEY (source_model, source_id)
                );
            """)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"فشل في إنشاء جدول 'mapping': {e}")
            raise

    def add_mapping(self, source_model, source_id, destination_id):
        """
        إضافة ربط جديد إلى قاعدة البيانات.

        Args:
            source_model (str): اسم الموديل في Odoo (مثل 'res.partner').
            source_id (int): المعرف الرقمي للسجل في نظام المصدر.
            destination_id (int): المعرف الرقمي للسجل في نظام الوجهة.
        """
        sql = "INSERT OR REPLACE INTO mapping (source_model, source_id, destination_id) VALUES (?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (source_model, source_id, destination_id))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"فشل في إضافة ربط لـ {source_model} ({source_id}): {e}")
            raise

    def get_destination_id(self, source_model, source_id):
        """
        جلب معرف الوجهة المقابل لمعرف المصدر.

        Args:
            source_model (str): اسم الموديل في Odoo.
            source_id (int): المعرف الرقمي للسجل في نظام المصدر.

        Returns:
            int or None: معرف الوجهة إذا تم العثور عليه، وإلا None.
        """
        sql = "SELECT destination_id FROM mapping WHERE source_model = ? AND source_id = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (source_model, source_id))
            result = cursor.fetchone()
            return result[0] if result else None
        except sqlite3.Error as e:
            print(f"فشل في البحث عن ربط لـ {source_model} ({source_id}): {e}")
            return None

    def close_connection(self):
        """
        إغلاق اتصال قاعدة البيانات بأمان.
        """
        if self.conn:
            self.conn.close()
            print("تم إغلاق اتصال قاعدة بيانات الربط.")

# --- مثال على كيفية الاستخدام (للاختبار فقط) ---
if __name__ == '__main__':
    # لتجنب حذف قاعدة البيانات في كل اختبار، يمكننا التحقق من وجودها
    db_file_path = 'sync_map.db'
    if os.path.exists(db_file_path):
        os.remove(db_file_path)
        print(f"تم حذف قاعدة البيانات القديمة: '{db_file_path}' للبدء من جديد.")
    
    try:
        # إنشاء كائن من مدير مفاتيح المزامنة
        key_manager = SyncKeyManager(db_file_path)

        print("\n--- اختبار إضافة بيانات ---")
        # إضافة بعض بيانات الربط التجريبية
        key_manager.add_mapping('res.partner', 101, 201)
        key_manager.add_mapping('res.partner', 102, 202)
        key_manager.add_mapping('account.move', 501, 901)
        print("تمت إضافة 3 سجلات ربط.")

        print("\n--- اختبار البحث عن بيانات ---")
        # البحث عن معرف موجود
        dest_id = key_manager.get_destination_id('res.partner', 101)
        print(f"البحث عن res.partner/101: وجدت المعرف في الوجهة -> {dest_id}") # المتوقع: 201

        # البحث عن معرف غير موجود
        dest_id_none = key_manager.get_destination_id('res.partner', 999)
        print(f"البحث عن res.partner/999: لم يتم العثور على معرف -> {dest_id_none}") # المتوقع: None

        # البحث في موديل آخر
        dest_id_invoice = key_manager.get_destination_id('account.move', 501)
        print(f"البحث عن account.move/501: وجدت المعرف في الوجهة -> {dest_id_invoice}") # المتوقع: 901

        # إغلاق الاتصال
        key_manager.close_connection()

    except Exception as e:
        print(f"حدث خطأ غير متوقع: {e}")