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
# يتم استيراد الوحدات هنا لتكون متاحة للتسجيل في محرك المزامنة.
from modules.contacts_sync import ContactSyncModule
from modules.company_sync import CompanySyncModule
from modules.accounts_sync import AccountSyncModule
from modules.journals_sync import JournalSyncModule
from modules.invoices_sync import InvoiceSyncModule
from modules.journal_entries_sync import JournalEntrySyncModule
from modules.taxes_sync import TaxSyncModule

def main():
    """
    الدالة الرئيسية لتشغيل عملية المزامنة.
    تقوم بتهيئة محرك المزامنة، وتسجيل الوحدات، ثم بدء عملية المزامنة.
    """
    print("===== بدء تطبيق المزامنة =====")
    try:
        # 1. تهيئة المحرك الأساسي
        # سيقوم المحرك تلقائيًا بتهيئة الاتصالات ومدير المفاتيح وقاعدة بيانات الربط.
        engine = SyncEngine()

        # 2. تسجيل وحدات المزامنة بالترتيب المنطقي الحاسم
        # الترتيب ضروري لضمان وجود البيانات المعتمد عليها مسبقًا في نظام الوجهة
        # قبل محاولة مزامنة السجلات التي تعتمد عليها.
        print("\n--- تسجيل وحدات المزامنة ---")
        engine.register_module(ContactSyncModule)       # البيانات الرئيسية (عملاء، موردون) - يجب مزامنتها أولاً.
        engine.register_module(CompanySyncModule)        # الشركات (مهم قبل الحسابات ودفاتر اليومية) - تعتمد عليها العديد من النماذج.
        engine.register_module(AccountSyncModule)        # أساس المحاسبة (شجرة الحسابات) - تعتمد عليها دفاتر اليومية والحركات.
        engine.register_module(JournalSyncModule)        # دفاتر اليومية (تعتمد على الحسابات) - ضرورية للفواتير وقيود اليومية.
        engine.register_module(TaxSyncModule)            # الضرائب (مهمة قبل الفواتير) - الفواتير تعتمد على سجلات الضرائب.
        engine.register_module(InvoiceSyncModule)        # المعاملات (الفواتير، تعتمد على كل ما سبق) - من النماذج الحركية الرئيسية.
        engine.register_module(JournalEntrySyncModule)   # المعاملات (القيود اليدوية، تعتمد على كل ما سبق) - من النماذج الحركية الرئيسية.
        print("--- اكتمل تسجيل الوحدات ---\n")
        
        # 3. تشغيل عملية المزامنة
        # يقوم محرك المزامنة بتشغيل الوحدات المسجلة بالترتيب.
        engine.run_sync()

    except Exception as e:
        # معالجة أي أخطاء غير متوقعة قد توقف التطبيق.
        print(f"\n[خطأ كارثي] توقف التطبيق بشكل غير متوقع. الخطأ: {e}")
        # في بيئة الإنتاج، يجب إضافة نظام تسجيل وإشعارات هنا (مثل إرسال بريد إلكتروني للمسؤول).
    finally:
        # يتم تنفيذ هذا الجزء دائمًا، سواء حدث خطأ أم لا.
        print("\n===== انتهاء تطبيق المزامنة =====")


if __name__ == '__main__':
    # هذه هي نقطة البداية عند تشغيل 'python main.py' مباشرة.
    # تضمن هذه الكتلة أن الدالة main() يتم استدعاؤها فقط عند تشغيل الملف كبرنامج رئيسي.
    main()
