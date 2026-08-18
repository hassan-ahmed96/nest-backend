# ربط الباك إند بـ Google Sheets فعلياً — دليل الإعداد

هذا الربط **مُعطَّل تلقائياً** حتى تُكمل الخطوات دي وتضبط متغيرَي البيئة
المطلوبين. قبلها، الباك إند بيشتغل عادي بدون أي تأثير.

## الخطوة 0: ارفع ملف الاستراتيجية على Google Drive (لو لسه ما عملتش كده)
افتح Google Drive → اسحب وأفلت `Nest_Strategy_Management.xlsx` → هيتحوّل
تلقائياً لملف Google Sheet. افتحه وخد الـ **Spreadsheet ID** من الرابط:
```
https://docs.google.com/spreadsheets/d/►هذا_الجزء_هو_المعرّف◄/edit
```

## الخطوة 1: أنشئ مشروع Google Cloud (مجاني)
1. افتح https://console.cloud.google.com
2. **New Project** → سمّه مثلاً `nest-backend` → Create.

## الخطوة 2: فعّل Google Sheets API
1. من القائمة: **APIs & Services → Library**.
2. ابحث عن **Google Sheets API** → اضغط **Enable**.

## الخطوة 3: أنشئ Service Account
1. **APIs & Services → Credentials → Create Credentials → Service Account**.
2. اسم مثلاً `nest-sheets-sync` → Create and Continue → Done (بدون أدوار
   إضافية، مش محتاجينها).
3. من قائمة الـ Service Accounts، افتح اللي أنشأته → تبويب **Keys** →
   **Add Key → Create new key → JSON** → هينزّل ملف `.json` على جهازك.
   **احتفظ بيه في مكان آمن — ده بيانات اعتماد حساسة.**

## الخطوة 4: شارك ملف الشيت مع الـ Service Account فقط
1. افتح ملف الـ JSON، هتلاقي فيه سطر `"client_email": "...@....iam.gserviceaccount.com"`.
2. ارجع لملف Nest Strategy على Google Sheets → **Share** → الصق الإيميل ده
   → اديله صلاحية **Editor** → Send (من غير إشعار بريد لو حبيت).

بكده الـ Service Account عنده وصول لملف واحد بس، مش أي حاجة تانية في
حسابك أو درايفك.

## الخطوة 5: اضبط متغيرات البيئة على Railway/Render
في تبويب **Variables/Environment** بعد النشر:
```
GOOGLE_SHEET_ID=<المعرّف من الخطوة 0>
GOOGLE_SERVICE_ACCOUNT_JSON=<محتوى ملف الـ JSON كامل كنص واحد (سطر واحد)>
```
لتحويل ملف الـ JSON لسطر واحد قبل اللصق:
```bash
python3 -c "import json;print(json.dumps(json.load(open('service-account.json'))))"
```

## التحقق بعد الضبط
```bash
curl https://<رابطك>/api/sheets-sync-status -H "X-API-Key: <مفتاحك>"
# المفروض يرجع: {"configured": true, "message": "جاهز للمزامنة..."}

curl -X POST https://<رابطك>/api/sync-to-sheets -H "X-API-Key: <مفتاحك>"
# هيضيف فعلياً كل الصفوف غير المُزامَنة لشيت "السجل اليومي"
```

بعد كده، المزامنة هتحصل تلقائياً كل يوم الساعة 23:55 UTC مع توليد
الملخص اليومي — **إضافة صفوف آمنة فقط (append)، بدون استبدال أي بيانات
موجودة أو لمس أي صف تاني في الملف.**

## ملاحظات أمان
- ملف الـ JSON بيانات اعتماد حساسة — لا تشاركه في الشات ولا ترفعه على
  GitHub. حطّه في متغيرات البيئة (Secrets) بس.
- الـ Service Account معاه صلاحية على ملف الشيت المحدد فقط، مش على درايفك كله.
- لو حبيت تلغي الربط في أي وقت: امسح متغيرَي البيئة، أو الغِ مشاركة
  الملف مع إيميل الـ Service Account من Google Sheets مباشرة.
