print("!!! تم تشغيل النسخة الجديدة من الملف !!!")

# -*- coding: utf-8 -*-
"""
المرحلة النهائية: ملف التشغيل الرئيسي المكتمل
main.py

الغرض:
- نقطة الدخول الرئيسية للتطبيق بأكمله.
- يقوم بتهيئة محرك المزامنة (SyncEngine).
- يقوم بتسجيل جميع وحدات المزامنة المطلوبة بالترتيب المنطقي الصحيح.
- يشغل عملية المزامنة الكاملة.
"""

from core.sync_engine import SyncEngine

# استيراد جميع وحدات المزامنة التي تم بناؤها
# يتم استيراد الوحدات هنا لتكون متاحة للتسجيل في محرك المزامنة.
from sync.modules.contacts_sync import ContactSyncModule
from sync.modules.company_sync import CompanySyncModule
from sync.modules.accounts_sync import AccountSyncModule
from sync.modules.journals_sync import JournalSyncModule
from sync.modules.invoices_sync import InvoiceSyncModule
from sync.modules.journal_entries_sync import JournalEntrySyncModule
from sync.modules.taxes_sync import TaxSyncModule

from services.logger_config import setup_logging
import logging

def main():
    """
    الدالة الرئيسية لتشغيل عملية المزامنة.
    تقوم بتهيئة محرك المزامنة، وتسجيل الوحدات، ثم بدء عملية المزامنة.
    """
    # تهيئة نظام السجلات في بداية تشغيل التطبيق.
    loggers = setup_logging()
    main_logger = loggers["main"]
    error_logger = loggers["error"]

    main_logger.info("===== بدء تطبيق المزامنة =====")
    try:
        # 1. تهيئة المحرك الأساسي
        # سيقوم المحرك تلقائيًا بتهيئة الاتصالات ومدير المفاتيح وقاعدة بيانات الربط.
        engine = SyncEngine(loggers) # تمرير كائنات المنسق إلى المحرك

        # 2. تسجيل وحدات المزامنة بالترتيب المنطقي الحاسم
        # الترتيب ضروري لضمان وجود البيانات المعتمد عليها مسبقًا في نظام الوجهة
        # قبل محاولة مزامنة السجلات التي تعتمد عليها.
        main_logger.info("\n--- تسجيل وحدات المزامنة ---")
        engine.register_module(ContactSyncModule)       # البيانات الرئيسية (عملاء، موردون) - يجب مزامنتها أولاً.
        engine.register_module(CompanySyncModule)        # الشركات (مهم قبل الحسابات ودفاتر اليومية) - تعتمد عليها العديد من النماذج.
        engine.register_module(AccountSyncModule)        # أساس المحاسبة (شجرة الحسابات) - تعتمد عليها دفاتر اليومية والحركات.
        engine.register_module(JournalSyncModule)        # دفاتر اليومية (تعتمد على الحسابات) - ضرورية للفواتير وقيود اليومية.
        engine.register_module(TaxSyncModule)            # الضرائب (مهمة قبل الفواتير) - الفواتير تعتمد على سجلات الضرائب.
        engine.register_module(InvoiceSyncModule)        # المعاملات (الفواتير، تعتمد على كل ما سبق) - من النماذج الحركية الرئيسية.
        engine.register_module(JournalEntrySyncModule)   # المعاملات (القيود اليدوية، تعتمد على كل ما سبق) - من النماذج الحركية الرئيسية.
        main_logger.info("--- اكتمل تسجيل الوحدات ---\n")
        
        # 3. تشغيل عملية المزامنة
        # يقوم محرك المزامنة بتشغيل الوحدات المسجلة بالترتيب.
        main_logger.info("[!] بدء تشغيل محرك المزامنة من main.py...")
        engine.run_sync()

    except Exception as e:
        # معالجة أي أخطاء غير متوقعة قد توقف التطبيق.
        error_logger.critical(f"\n[خطأ كارثي] توقف التطبيق بشكل غير متوقع. الخطأ: {e}")
        # في بيئة الإنتاج، يجب إضافة نظام تسجيل وإشعارات هنا (مثل إرسال بريد إلكتروني للمسؤول).
    finally:
        # يتم تنفيذ هذا الجزء دائمًا، سواء حدث خطأ أم لا.
        main_logger.info("\n===== انتهاء تطبيق المزامنة =====")


if __name__ == '__main__':
    print("!!! على وشك استدعاء الدالة الرئيسية main() !!!")
    # هذه هي نقطة البداية عند تشغيل 'python main.py' مباشرة.
    # تضمن هذه الكتلة أن الدالة main() يتم استدعاؤها فقط عند تشغيل الملف كبرنامج رئيسي.
    main()
