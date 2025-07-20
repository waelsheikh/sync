# -*- coding: utf-8 -*-
"""
المرحلة 4: النواة الأساسية للمزامنة
sync_engine.py

الغرض:
- تجميع كل المكونات الأساسية (Config, SyncKey, Connectors) في مكان واحد.
- إدارة دورة حياة عملية المزامنة بأكملها.
- توفير إطار عمل لتسجيل وتشغيل وحدات المزامنة المتخصصة (التي ستُبنى لاحقاً).
"""

from config_manager import ConfigManager
from sync_key_manager import SyncKeyManager
from odoo_connector import OdooConnector

class SyncEngine:
    """
    المنسق الرئيسي لعملية المزامنة. يقوم بتهيئة جميع الخدمات
    وتشغيل وحدات المزامنة المسجلة بالترتيب.
    """
    def __init__(self):
        """
        تهيئة النواة الأساسية للمزامنة.
        """
        print("="*50)
        print("بدء تشغيل محرك المزامنة (Sync Engine)...")
        self.config_manager = None
        self.key_manager = None
        self.source_conn = None
        self.dest_conn = None
        self.sync_modules = []
        self._initialize_services()
        print("="*50)

    def _initialize_services(self):
        """
        يقوم بتحميل وتهيئة جميع الخدمات الأساسية اللازمة للمزامنة.
        """
        try:
            # 1. تحميل الإعدادات
            self.config_manager = ConfigManager()

            # 2. تهيئة مدير مفاتيح المزامنة (الذاكرة)
            self.key_manager = SyncKeyManager()

            # 3. إنشاء اتصال بنظام المصدر (Odoo Community)
            community_creds = self.config_manager.get_community_credentials()
            self.source_conn = OdooConnector(community_creds).get_api()

            # 4. إنشاء اتصال بنظام الوجهة (Odoo Online)
            online_creds = self.config_manager.get_online_credentials()
            self.dest_conn = OdooConnector(online_creds).get_api()

            print("\n[نجاح] تم تهيئة جميع الخدمات الأساسية بنجاح.")

        except (FileNotFoundError, ValueError, ConnectionError) as e:
            print(f"\n[فشل حرج] فشل في تهيئة الخدمات الأساسية: {e}")
            print("لا يمكن متابعة عملية المزامنة. يرجى مراجعة الأخطاء أعلاه.")
            raise  # إيقاف التنفيذ بالكامل لأن المزامنة مستحيلة بدون هذه الخدمات

    def register_module(self, module_class):
        """
        تسجيل وحدة مزامنة متخصصة لتشغيلها لاحقًا.
        
        Args:
            module_class: الكلاس الخاص بوحدة المزامنة (وليس كائنًا منه).
        """
        if not hasattr(module_class, 'run'):
            raise TypeError(f"فشلت محاولة تسجيل الوحدة {module_class.__name__}: يجب أن تحتوي على دالة 'run'.")
            
        # إنشاء كائن من الوحدة وتمرير الخدمات الأساسية إليه
        module_instance = module_class(
            source_conn=self.source_conn,
            dest_conn=self.dest_conn,
            key_manager=self.key_manager
        )
        self.sync_modules.append(module_instance)
        print(f"تم تسجيل وحدة المزامنة: {module_class.__name__}")

    def run_sync(self):
        """
        تشغيل جميع وحدات المزامنة المسجلة بالترتيب.
        """
        if not self.sync_modules:
            print("\n[تحذير] لا توجد وحدات مزامنة مسجلة. لم يتم تنفيذ أي شيء.")
            return

        print("\n" + "="*50)
        print("بدء عملية المزامنة الكاملة...")
        print("="*50)

        for module in self.sync_modules:
            try:
                module_name = module.__class__.__name__
                print(f"\n--- [جارٍ التشغيل] وحدة: {module_name} ---")
                module.run()
                print(f"--- [اكتمل] وحدة: {module_name} ---")
            except Exception as e:
                print(f"\n[خطأ فادح] فشلت وحدة '{module_name}' وتوقفت عملية المزامنة.")
                print(f"تفاصيل الخطأ: {e}")
                # في بيئة الإنتاج، قد ترغب في إرسال إشعار بالبريد الإلكتروني هنا
                break  # إيقاف المزامنة عند حدوث خطأ فادح في إحدى الوحدات

        print("\n" + "="*50)
        print("اكتملت عملية المزامنة الكاملة.")
        print("="*50)
        
        # إغلاق الاتصالات في النهاية
        self.key_manager.close_connection()

# --- هذا الملف هو إطار عمل ولا يتم تشغيله مباشرة ---
# --- سيتم استيراده وتشغيله من ملف رئيسي لاحقًا (مثل main.py) ---
if __name__ == '__main__':
    print("هذا الملف هو النواة الأساسية (Engine) ولا يُفترض تشغيله بشكل مباشر.")
    print("سيتم استيراده واستخدامه من خلال ملف التشغيل الرئيسي (main.py).")
    
    # يمكنك وضع كود تجريبي هنا إذا أردت، لكنه ليس ضروريًا
    # مثال:
    # try:
    #     engine = SyncEngine()
    #     # هنا سنسجل الوحدات الفعلية في المستقبل
    #     # engine.register_module(ContactSyncModule) 
    #     # engine.run_sync()
    # except Exception as e:
    #     print("توقف المحرك بسبب خطأ.")
