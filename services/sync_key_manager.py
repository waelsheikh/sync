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
    يتم استخدام هذا المدير لتخزين الروابط بين معرفات المصدر والوجهة
    للسجلات التي لا تحتوي على حقول `x_sync_id` خاصة بها في الوجهة،
    أو كطبقة احتياطية للبحث عن الروابط.
    """
    def __init__(self, db_file='sync_map.db'):
        """
        تهيئة مدير مفتاح المزامنة. يتصل بقاعدة البيانات وينشئ الجدول إذا لم يكن موجودًا.

        Args:
            db_file (str): اسم ملف قاعدة بيانات SQLite (الافتراضي هو 'sync_map.db').
        Raises:
            sqlite3.Error: إذا حدث خطأ أثناء الاتصال بقاعدة البيانات أو إنشاء الجدول.
        """
        self.db_file = db_file
        self.conn = None
        try:
            # الاتصال بقاعدة البيانات (سيتم إنشاؤها إذا لم تكن موجودة).
            self.conn = sqlite3.connect(self.db_file)
            # إنشاء جدول الربط إذا لم يكن موجودًا.
            self._create_table()
            print(f"تم الاتصال بقاعدة بيانات الربط بنجاح: '{self.db_file}'")
        except sqlite3.Error as e:
            print(f"حدث خطأ في قاعدة البيانات: {e}")
            raise

    def _create_table(self):
        """
        إنشاء جدول الربط (mapping) إذا لم يكن موجودًا.
        الجدول يخزن العلاقة بين معرفات المصدر والوجهة لكل نموذج.
        `source_model`: اسم النموذج (مثال: 'res.partner').
        `source_id`: المعرف الفريد للسجل في نظام المصدر.
        `destination_id`: المعرف الفريد للسجل المقابل في نظام الوجهة.
        `PRIMARY KEY (source_model, source_id)`: يضمن أن كل ربط فريد.
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
        إضافة أو تحديث ربط جديد في قاعدة البيانات.
        إذا كان الربط موجودًا بالفعل، فسيتم تحديث `destination_id`.

        Args:
            source_model (str): اسم الموديل في Odoo (مثل 'res.partner').
            source_id (int): المعرف الرقمي للسجل في نظام المصدر.
            destination_id (int): المعرف الرقمي للسجل في نظام الوجهة.
        Raises:
            sqlite3.Error: إذا فشلت عملية الإضافة أو التحديث.
        """
        # `INSERT OR REPLACE` يضمن أننا إما نضيف ربطًا جديدًا أو نحدث ربطًا موجودًا.
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
        جلب معرف الوجهة المقابل لمعرف المصدر من قاعدة بيانات الربط.

        Args:
            source_model (str): اسم الموديل في Odoo.
            source_id (int): المعرف الرقمي للسجل في نظام المصدر.

        Returns:
            int or None: معرف الوجهة إذا تم العثور عليه، وإلا None.
        Raises:
            sqlite3.Error: إذا فشلت عملية البحث.
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

    def get_all_source_ids_for_model(self, source_model):
        """
        جلب جميع معرفات المصدر المخزنة لنموذج معين.

        Args:
            source_model (str): اسم الموديل في Odoo.

        Returns:
            list: قائمة بمعرفات المصدر (int) لهذا النموذج.
        Raises:
            sqlite3.Error: إذا فشلت عملية البحث.
        """
        sql = "SELECT source_id FROM mapping WHERE source_model = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (source_model,))
            results = cursor.fetchall()
            return [row[0] for row in results]
        except sqlite3.Error as e:
            print(f"فشل في جلب جميع معرفات المصدر لـ {source_model}: {e}")
            raise

    def remove_mapping(self, source_model, source_id):
        """
        إزالة ربط معين من قاعدة البيانات.

        Args:
            source_model (str): اسم الموديل في Odoo.
            source_id (int): المعرف الرقمي للسجل في نظام المصدر.
        Raises:
            sqlite3.Error: إذا فشلت عملية الإزالة.
        """
        sql = "DELETE FROM mapping WHERE source_model = ? AND source_id = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (source_model, source_id))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"فشل في إزالة ربط لـ {source_model} ({source_id}): {e}")
            raise

    def close_connection(self):
        """
        إغلاق اتصال قاعدة البيانات بأمان.
        يجب استدعاء هذه الدالة عند الانتهاء من استخدام مدير المفاتيح.
        """
        if self.conn:
            self.conn.close()
            print("تم إغلاق اتصال قاعدة بيانات الربط.")

# --- مثال على كيفية الاستخدام (للاختبار فقط) ---
# يتم تشغيل هذا الجزء فقط إذا تم تشغيل الملف مباشرة (وليس عند استيراده كوحدة).
if __name__ == '__main__':
    # لتجنب حذف قاعدة البيانات في كل اختبار، يمكننا التحقق من وجودها.
    db_file_path = 'sync_map.db'
    if os.path.exists(db_file_path):
        os.remove(db_file_path)
        print(f"تم حذف قاعدة البيانات القديمة: '{db_file_path}' للبدء من جديد.")
    
    try:
        # إنشاء كائن من مدير مفاتيح المزامنة.
        key_manager = SyncKeyManager(db_file_path)

        print("\n--- اختبار إضافة بيانات ---")
        # إضافة بعض بيانات الربط التجريبية.
        key_manager.add_mapping('res.partner', 101, 201)
        key_manager.add_mapping('res.partner', 102, 202)
        key_manager.add_mapping('account.move', 501, 901)
        print("تمت إضافة 3 سجلات ربط.")

        print("\n--- اختبار البحث عن بيانات ---")
        # البحث عن معرف موجود.
        dest_id = key_manager.get_destination_id('res.partner', 101)
        print(f"البحث عن res.partner/101: وجدت المعرف في الوجهة -> {dest_id}") # المتوقع: 201

        # البحث عن معرف غير موجود.
        dest_id_none = key_manager.get_destination_id('res.partner', 999)
        print(f"البحث عن res.partner/999: لم يتم العثور على معرف -> {dest_id_none}") # المتوقع: None

        # البحث في موديل آخر.
        dest_id_invoice = key_manager.get_destination_id('account.move', 501)
        print(f"البحث عن account.move/501: وجدت المعرف في الوجهة -> {dest_id_invoice}") # المتوقع: 901

        print("\n--- اختبار جلب جميع معرفات المصدر لنموذج ---")
        all_partner_src_ids = key_manager.get_all_source_ids_for_model('res.partner')
        print(f"جميع معرفات المصدر لـ res.partner: {all_partner_src_ids}") # المتوقع: [101, 102]

        print("\n--- اختبار إزالة ربط ---")
        key_manager.remove_mapping('res.partner', 101)
        print("تمت إزالة ربط res.partner/101.")
        dest_id_after_remove = key_manager.get_destination_id('res.partner', 101)
        print(f"البحث عن res.partner/101 بعد الإزالة: {dest_id_after_remove}") # المتوقع: None

        # إغلاق الاتصال.
        key_manager.close_connection()

    except Exception as e:
        print(f"حدث خطأ غير متوقع: {e}")