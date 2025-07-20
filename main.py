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

from sync_engine import SyncEngine

# استيراد جميع وحدات المزامنة التي تم بناؤها
from modules.contacts_sync import ContactSyncModule
from modules.accounts_sync import AccountSyncModule
from modules.journals_sync import JournalSyncModule
from modules.invoices_sync import InvoiceSyncModule
from modules.journal_entries_sync import JournalEntrySyncModule

def main():
    """
    الدالة الرئيسية لتشغيل عملية المزامنة.
    """
    print("===== بدء تطبيق المزامنة =====")
    try:
        # 1. تهيئة المحرك الأساسي
        # سيقوم المحرك تلقائيًا بتهيئة الاتصالات ومدير المفاتيح
        engine = SyncEngine()

        # 2. تسجيل وحدات المزامنة بالترتيب المنطقي الحاسم
        # الترتيب ضروري لضمان وجود البيانات المعتمد عليها مسبقًا.
        print("\n--- تسجيل وحدات المزامنة ---")
        engine.register_module(ContactSyncModule)       # البيانات الرئيسية (عملاء، موردون)
        engine.register_module(AccountSyncModule)        # أساس المحاسبة (شجرة الحسابات)
        engine.register_module(JournalSyncModule)        # دفاتر اليومية (تعتمد على الحسابات)
        engine.register_module(InvoiceSyncModule)        # المعاملات (الفواتير، تعتمد على كل ما سبق)
        engine.register_module(JournalEntrySyncModule)   # المعاملات (القيود اليدوية، تعتمد على كل ما سبق)
        print("--- اكتمل تسجيل الوحدات ---\n")
        
        # 3. تشغيل عملية المزامنة
        engine.run_sync()

    except Exception as e:
        print(f"\n[خطأ كارثي] توقف التطبيق بشكل غير متوقع. الخطأ: {e}")
        # في بيئة الإنتاج، يجب إضافة نظام تسجيل وإشعارات هنا.
    finally:
        print("\n===== انتهاء تطبيق المزامنة =====")


if __name__ == '__main__':
    # هذه هي نقطة البداية عند تشغيل 'python main.py'
    main()