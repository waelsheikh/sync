import logging
import os

def setup_logging():
    # إنشاء مجلد السجلات إذا لم يكن موجودًا
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # تهيئة المنسق الرئيسي
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # تعيين أدنى مستوى للسجل

    # إزالة أي متحكمات موجودة لتجنب تكرار السجلات
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 1. متحكم الأخطاء (error.log)
    error_handler = logging.FileHandler(os.path.join(log_dir, "error.log"), encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)

    # 2. متحكم النشاط العام (activity.log)
    activity_handler = logging.FileHandler(os.path.join(log_dir, "activity.log"), encoding="utf-8")
    activity_handler.setLevel(logging.INFO)
    activity_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    activity_handler.setFormatter(activity_formatter)
    root_logger.addHandler(activity_handler)

    # 3. متحكم تفاصيل المزامنة (sync.log)
    sync_handler = logging.FileHandler(os.path.join(log_dir, "sync.log"), encoding="utf-8")
    sync_handler.setLevel(logging.DEBUG) # يمكن تغييرها إلى INFO في بيئة الإنتاج لتقليل التفاصيل
    sync_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    sync_handler.setFormatter(sync_formatter)
    root_logger.addHandler(sync_handler)

    # 4. متحكم الكونسول (لإظهار رسائل INFO+ على الشاشة)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # تعريف منسقات محددة يمكن استخدامها في أجزاء مختلفة من الكود
    loggers = {
        "error": logging.getLogger("error_logger"),
        "activity": logging.getLogger("activity_logger"),
        "sync": logging.getLogger("sync_logger"),
        "main": logging.getLogger("main_app"), # منسق خاص لـ main.py
        "engine": logging.getLogger("sync_engine"), # منسق خاص لـ SyncEngine
        "connector": logging.getLogger("odoo_connector"), # منسق خاص لـ OdooConnector
        "key_manager": logging.getLogger("sync_key_manager"), # منسق خاص لـ SyncKeyManager
        "config_manager": logging.getLogger("config_manager"), # منسق خاص لـ ConfigManager
        # منسقات لوحدات المزامنة
        "contacts_sync": logging.getLogger("contacts_sync_module"),
        "company_sync": logging.getLogger("company_sync_module"),
        "accounts_sync": logging.getLogger("accounts_sync_module"),
        "journals_sync": logging.getLogger("journals_sync_module"),
        "taxes_sync": logging.getLogger("taxes_sync_module"),
        "invoices_sync": logging.getLogger("invoices_sync_module"),
        "journal_entries_sync": logging.getLogger("journal_entries_sync_module"),
    }

    # تعيين المتحكمات لكل منسق محدد
    for name, logger_obj in loggers.items():
        logger_obj.addHandler(console_handler) # إضافة متحكم الكونسول لجميع المنسقات
        if name == "error":
            logger_obj.addHandler(error_handler)
        elif name == "activity":
            logger_obj.addHandler(activity_handler)
        elif name == "sync":
            logger_obj.addHandler(sync_handler)
        else: # جميع المنسقات الأخرى ترسل إلى activity و sync
            logger_obj.addHandler(activity_handler)
            logger_obj.addHandler(sync_handler)
        logger_obj.propagate = False # منع تكرار السجلات من المنسقات الفرعية

    return loggers