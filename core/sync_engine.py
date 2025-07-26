# -*- coding: utf-8 -*-
"""
المرحلة 4: النواة الأساسية للمزامنة
sync_engine.py

الغرض:
- تجميع كل المكونات الأساسية (Config, SyncKey, Connectors) في مكان واحد.
- إدارة دورة حياة عملية المزامنة بأكملها.
- توفير إطار عمل لتسجيل وتشغيل وحدات المزامنة المتخصصة (التي ستُبنى لاحقاً).
"""

from services.config_manager import ConfigManager
from services.sync_key_manager import SyncKeyManager
from services.odoo_connector import OdooConnector
from services.logger_config import setup_logging
import logging

class SyncEngine:
    """
    المنسق الرئيسي لعملية المزامنة. يقوم بتهيئة جميع الخدمات
    وتشغيل وحدات المزامنة المسجلة بالترتيب.
    """
    def __init__(self, loggers=None):
        """
        تهيئة النواة الأساسية للمزامنة.
        """
        # تهيئة نظام السجلات.
        self.loggers = loggers if loggers is not None else setup_logging()
        self.engine_logger = self.loggers["engine"]
        self.error_logger = self.loggers["error"]
        self.activity_logger = self.loggers["activity"]

        self.engine_logger.info("="*50)
        self.engine_logger.info("بدء تشغيل محرك المزامنة (Sync Engine)...")
        self.config_manager = None
        self.key_manager = None
        self.source_conn = None
        self.dest_conn = None
        self.sync_modules = []
        # قراءة آخر وقت مزامنة من الملف، أو تعيين تاريخ قديم إذا لم يكن موجودًا.
        self.last_sync_time = self._read_last_sync_time()
        # تهيئة جميع الخدمات الأساسية المطلوبة للمزامنة.
        self._initialize_services()
        self.engine_logger.info("="*50)

    def _read_last_sync_time(self):
        """
        يقرأ آخر طابع زمني للمزامنة من ملف `last_sync_time.txt`.
        هذا الطابع الزمني يستخدم لتحديد السجلات التي تم تعديلها منذ آخر مزامنة ناجحة.

        Returns:
            str: الطابع الزمني لآخر مزامنة بتنسيق YYYY-MM-DD HH:MM:SS.
        """
        try:
            with open('last_sync_time.txt', 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            # إذا لم يكن الملف موجودًا، فهذه هي المزامنة الأولى.
            # يتم إرجاع تاريخ قديم جدًا لضمان جلب جميع السجلات في التشغيل الأول.
            self.activity_logger.info("ملف last_sync_time.txt غير موجود. ستبدأ مزامنة كاملة.")
            return "1970-01-01 00:00:00"  # تاريخ قديم جدًا لجلب كل شيء

    def _write_last_sync_time(self):
        """
        يكتب الطابع الزمني الحالي (بتوقيت UTC) إلى ملف `last_sync_time.txt`.
        يتم استدعاء هذه الدالة بعد اكتمال جميع وحدات المزامنة بنجاح.
        """
        from datetime import datetime
        # الحصول على الوقت الحالي بتوقيت UTC لضمان التناسق مع تخزين Odoo للوقت.
        current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with open('last_sync_time.txt', 'w') as f:
            f.write(current_time)
        self.activity_logger.info(f"تم حفظ آخر وقت مزامنة: {current_time}")

    def _initialize_services(self):
        """
        يقوم بتحميل وتهيئة جميع الخدمات الأساسية اللازمة للمزامنة.
        يتضمن ذلك مدير الإعدادات، مدير مفاتيح المزامنة، وموصلات Odoo للمصدر والوجهة.
        كما يتحقق من وجود الحقول المخصصة الضرورية في نظام Odoo الوجهة.

        Raises:
            FileNotFoundError: إذا لم يتم العثور على ملف الإعدادات.
            ValueError: إذا كانت بيانات الاعتماد غير صحيحة أو غير مكتملة.
            ConnectionError: إذا فشل الاتصال بخوادم Odoo.
        """
        try:
            # 1. تحميل الإعدادات من ملف config.ini.
            self.config_manager = ConfigManager()

            # 2. تهيئة مدير مفاتيح المزامنة (الذاكرة المحلية).
            self.key_manager = SyncKeyManager()

            # 3. إنشاء اتصال بنظام المصدر (Odoo Community).
            community_creds = self.config_manager.get_community_credentials()
            self._source_connector = OdooConnector(community_creds, logger=self.loggers.get("connector"))
            self.source_conn = self._source_connector.get_api()
            self.loggers["engine"].info("تم الاتصال وتسجيل الدخول بنجاح إلى Odoo المصدر.")


            # 4. إنشاء اتصال بنظام الوجهة (Odoo Online).
            online_creds = self.config_manager.get_online_credentials()
            self._dest_connector = OdooConnector(online_creds, logger=self.loggers.get("connector"))
            self.dest_conn = self._dest_connector.get_api()
            self.loggers["engine"].info("تم الاتصال وتسجيل الدخول بنجاح إلى Odoo الوجهة.")


            # 5. التأكد من وجود الحقول المخصصة في نظام Odoo الوجهة.
            self.engine_logger.info("\n[جاري التحقق] من الحقول المخصصة في نظام الوجهة...")
            
            fields_to_ensure = [
                ('res.partner', 'x_partner_sync_id', 'Partner Sync ID', 'char'),
                ('res.company', 'x_company_sync_id', 'Company Sync ID', 'char'),
                ('account.account', 'x_account_sync_id', 'Account Sync ID', 'char'),
                ('account.journal', 'x_journal_sync_id', 'Journal Sync ID', 'char'),
                ('account.tax', 'x_tax_sync_id', 'Tax Sync ID', 'char'),
                ('account.move', 'x_move_sync_id', 'Move Sync ID', 'char'),
                ('account.move', 'x_original_source_id', 'Original Source ID', 'integer'),
                ('account.move', 'x_original_write_date', 'Original Write Date', 'datetime'),
            ]

            for model, field_name, label, field_type in fields_to_ensure:
                self._dest_connector.ensure_custom_field(model, field_name, label, field_type)
            
            self.engine_logger.info("  - تم التحقق بنجاح من جميع الحقول المخصصة.")
            self.engine_logger.info("\n[نجاح] تم تهيئة جميع الخدمات الأساسية بنجاح.")

        except (FileNotFoundError, ValueError, ConnectionError) as e:
            self.error_logger.critical(f"\n[فشل حرج] فشل في تهيئة الخدمات الأساسية: {e}")
            self.error_logger.critical("لا يمكن متابعة عملية المزامنة. يرجى مراجعة الأخطاء أعلاه.")
            raise

    def register_module(self, module_class):
        """
        تسجيل وحدة مزامنة متخصصة لتشغيلها لاحقًا.
        يتم إنشاء كائن من الوحدة وتمرير الاتصالات ومدير المفاتيح وآخر وقت مزامنة إليها.

        Args:
            module_class: الكلاس الخاص بوحدة المزامنة (وليس كائنًا منه).
        Raises:
            TypeError: إذا كانت الوحدة لا تحتوي على دالة `run`.
        """
        if not hasattr(module_class, 'run'):
            raise TypeError(f"فشلت محاولة تسجيل الوحدة {module_class.__name__}: يجب أن تحتوي على دالة 'run'.")
            
        # إنشاء كائن من الوحدة وتمرير الخدمات الأساسية إليه.
        module_instance = module_class(
            source_conn=self.source_conn,
            dest_conn=self.dest_conn,
            key_manager=self.key_manager,
            last_sync_time=self.last_sync_time,
            loggers=self.loggers # تمرير كائنات المنسق إلى الوحدة
        )
        self.sync_modules.append(module_instance)
        self.engine_logger.info(f"تم تسجيل وحدة المزامنة: {module_class.__name__}")

    def run_sync(self):
        """
        تشغيل جميع وحدات المزامنة المسجلة بالترتيب.
        يتم التعامل مع الأخطاء على مستوى الوحدة لضمان استمرارية العملية قدر الإمكان.
        """
        if not self.sync_modules:
            self.activity_logger.warning("\n[تحذير] لا توجد وحدات مزامنة مسجلة. لم يتم تنفيذ أي شيء.")
            return

        self.engine_logger.info("\n" + "="*50)
        self.engine_logger.info("بدء عملية المزامنة الكاملة...")
        self.engine_logger.info("*** تم الوصول إلى دالة run_sync في SyncEngine ***")
        self.engine_logger.info("="*50)

        for module in self.sync_modules:
            try:
                module_name = module.__class__.__name__
                self.engine_logger.info(f"\n--- [جارٍ التشغيل] وحدة: {module_name} ---")
                module.run()
                self.engine_logger.info(f"--- [اكتمل] وحدة: {module_name} ---")
            except Exception as e:
                # تسجيل الخطأ وإيقاف المزامنة إذا حدث خطأ فادح في إحدى الوحدات.
                self.error_logger.critical(f"\n[خطأ فادح] فشلت وحدة '{module_name}' وتوقفت عملية المزامنة.")
                self.error_logger.critical(f"تفاصيل الخطأ: {e}")
                # في بيئة الإنتاج، قد ترغب في إرسال إشعار بالبريد الإلكتروني هنا.
                break  # إيقاف المزامنة عند حدوث خطأ فادح في إحدى الوحدات.

        self.engine_logger.info("\n" + "="*50)
        self.engine_logger.info("اكتملت عملية المزامنة الكاملة.")
        self.engine_logger.info("="*50)
        
        # إغلاق الاتصالات بقاعدة بيانات الربط وحفظ آخر وقت مزامنة.
        self.key_manager.close_connection()
        self._write_last_sync_time()

# --- هذا الملف هو إطار عمل ولا يتم تشغيله مباشرة ---
# --- سيتم استيراده وتشغيله من ملف رئيسي لاحقًا (مثل main.py) ---
if __name__ == '__main__':
    # هذا الملف هو النواة الأساسية (Engine) ولا يُفترض تشغيله بشكل مباشر.
    # تضمن هذه الكتلة أن الدالة main() يتم استدعاؤها فقط عند تشغيل الملف كبرنامج رئيسي.
    print("هذا الملف هو النواة الأساسية (Engine) ولا يُفترض تشغيله بشكل مباشر.")
    print("سيتم استيراده واستخدامه من خلال ملف التشغيل الرئيسي (main.py).")
    
    # يمكنك وضع كود تجريبي هنا إذا أردت، لكنه ليس ضروريًا.
    # مثال:
    # try:
    #     engine = SyncEngine()
    #     # هنا سنسجل الوحدات الفعلية في المستقبل.
    #     # engine.register_module(ContactSyncModule) 
    #     # engine.run_sync()
    # except Exception as e:
    #     print("توقف المحرك بسبب خطأ.")
