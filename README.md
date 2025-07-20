# 🔁 Odoo Sync Tool

أداة بايثون لمزامنة البيانات من **Odoo Community (محلي)** إلى **Odoo Online (سحابي)**، باستخدام واجهات XML-RPC وتصدير CSV. الهدف هو استخدام Odoo Online كمركز تقارير فقط دون تكرار البيانات يدويًا.

---

## 🚀 الميزات

- ✅ مزامنة الشركاء (Contacts)
- ✅ مزامنة المنتجات وفئاتها
- ✅ مزامنة الفواتير والمشتريات والمبيعات
- ✅ مزامنة القيود اليومية اليومية (Journal Entries + Lines)
- ✅ يدعم الحقول المخصصة لربط البيانات بين النظامين
- ✅ سجل كامل للأخطاء والعمليات في ملفات `.log`

---

## ⚙️ المتطلبات

- Python 3.10 أو أحدث
- مكتبة `xmlrpc.client` (مضمنة في بايثون)
- إعداد بيئة افتراضية (اختياري لكن مفضل)

---

## 📂 الإعداد

1. **انسخ ملف البيئة**:

   ```bash
   cp sync_odoo_data.env.example sync_odoo_data.env




Sync1002/
├── sync_odoo.py
├── models/
│   └── res_partner.py
│   └── account_move.py
│   └── ...
├── utils/
│   └── logger.py
│   └── helpers.py
├── sync_odoo_data.env
├── .gitignore
└── README.md




---

## ✅ خطوات الحفظ والدفع إلى GitHub:

نفّذ الأوامر التالية:

```bash
echo (الصق المحتوى أعلاه في README.md أو أنشئه يدويًا) > README.md
git add README.md
git commit -m "📝 إضافة ملف README.md لتوثيق المشروع"
git push
