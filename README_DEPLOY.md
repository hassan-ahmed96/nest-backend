# نشر Nest Backend على استضافة حقيقية (Railway / Render)

هذا الملف يشرح الخطوات المطلوبة منك لجعل الـ Backend يعمل 24/7 على الإنترنت.
**ملاحظة مهمة**: إنشاء الحساب وربط الخدمة يتطلب دخولك أنت (بريدك، حسابك) —
لا يمكن لأي مساعد آلي إنشاء حساب استضافة أو الدفع نيابة عنك. الخطوات هنا
تأخذ 5-10 دقائق تقريباً.

## الخيار الأول: Railway (الأسهل والأسرع)

1. افتح https://railway.app وسجّل دخول بحساب GitHub أو بريدك.
2. اضغط **New Project → Deploy from GitHub repo** (لو الكود مرفوع على GitHub)
   أو **Empty Project** ثم استخدم Railway CLI لرفع المجلد مباشرة:
   ```bash
   npm i -g @railway/cli
   railway login
   cd nest_backend
   railway init
   railway up
   ```
3. من تبويب **Variables** في المشروع، أضف متغيّر:
   `NEST_API_KEY = <مفتاح قوي وطويل من اختيارك>`
4. Railway هيكتشف `Dockerfile` تلقائياً ويبني وينشر الخدمة.
5. من تبويب **Settings → Networking**، فعّل **Generate Domain** — هتاخد رابط
   عام زي `https://nest-backend-production.up.railway.app`.
6. جرّب: `curl https://<رابطك>/api/health` ولازم يرجع `{"status":"ok"}`.

## الخيار الثاني: Render

1. افتح https://render.com وسجّل دخول.
2. **New → Web Service** → اختَر **Public Git Repository** (ارفع الكود على
   GitHub أولاً) أو استخدم **Deploy an existing image**.
3. Render هيقرأ `render.yaml` تلقائياً لو موجود في نفس الريبو (Blueprint).
4. أضف متغيّر البيئة `NEST_API_KEY` من تبويب **Environment**.
5. بعد النشر هتاخد رابط زي `https://nest-backend.onrender.com`.

## بعد ما يبقى شغّال

- ابعتلي الرابط العام + مفتاح الـ API الجديد (في مكان آمن، مش هنا في الشات
  لو حابب، أو هنا لو مرتاح — على حسب رغبتك)، وهراجع إن كل الـ endpoints
  شغالة صح على الاستضافة الجديدة.
- الملخص اليومي (`/api/daily-digests`) هيفضل يتوّلد تلقائياً كل يوم الساعة
  23:55 UTC طالما الخدمة شغالة، من غير أي تدخل يدوي.
- خطوة لاحقة منفصلة (تحتاج موافقتك الصريحة): ربط هذا الـ Backend المستضاف
  فعلياً بملف Google Sheets (بدل ملف Excel محلي) — يتطلب صلاحيات Google
  Sheets API حقيقية سأعرضها عليك بالتفصيل قبل أي تفعيل.

## ملفات النشر الجاهزة في هذا المجلد
- `Dockerfile` — لبناء صورة الحاوية.
- `requirements.txt` — مكتبات Python المطلوبة.
- `railway.toml` — إعدادات Railway.
- `render.yaml` — إعدادات Render (Blueprint).
- `.env.example` — نموذج متغيرات البيئة (انسخه إلى `.env` محلياً لو حبيت
  تجرّب بمفتاح مختلف قبل النشر).
