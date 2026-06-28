# Workflow: مدیریت موجودی انبارهای کارگاه

## هدف
نگه‌داشتن یک تصویر واحد و به‌روز از موجودی همه‌ی انبارهای کارگاه‌ها روی
Google Sheets، به‌طوری که:
- بشود موجودی هر کالا را در همه‌ی انبارها هم‌زمان دید.
- قبل از هر درخواست خرید جدید، اول چک شود کالای مشابه در انبار دیگری
  موجود است یا نه (و در آن صورت انتقال داخلی جای خرید جدید پیشنهاد شود).
- تاریخچه‌ی کامل ورود/خروج/انتقال هر کالا (Transactions) قابل پیگیری باشد.

## فایل‌های اصلی این سیستم
- ابزار اجرایی: `tools/inventory.py` (CLI با subcommand)
- لایه‌ی ارتباط با گوگل: `tools/sheets_client.py`
- تنظیمات: `.env` (کلیدهای `GOOGLE_SERVICE_ACCOUNT_FILE`, `INVENTORY_SPREADSHEET_ID`)
- کلید Service Account: `credentials.json` (در ریشه پروژه، هرگز commit نشود)

## پیش‌نیاز راه‌اندازی (یک‌بار)
1. ساخت Service Account در Google Cloud Console، فعال‌سازی Google Sheets API،
   دانلود کلید JSON → ذخیره در ریشه‌ی پروژه با نام `credentials.json`.
2. ساخت یک Google Sheet خالی توسط کاربر (نه توسط Service Account — چون
   Service Account اگر خودش بسازد، فایل در Drive خودش می‌ماند و کاربر بهش
   دسترسی مستقیم در Drive ندارد مگر با Scope اضافه‌ی Drive).
3. Share کردن آن شیت با ایمیل Service Account (نقش Editor).
4. آیدی شیت (از URL، بین `/d/` و `/edit`) در `.env` به‌عنوان
   `INVENTORY_SPREADSHEET_ID` ثبت شود.
5. اجرای `python tools/inventory.py setup` برای ساخت تب‌ها و هدرها.

## ساختار داده (تب‌های شیت)
- **Warehouses**: warehouse_name, location, contact
- **Items**: item_name, unit, min_stock, category — کاتالوگ کلی کالاها
  (min_stock اختیاری است؛ اگر صفر باشد در گزارش low-stock نادیده گرفته می‌شود)
- **Stock**: warehouse_name, item_name, quantity, last_updated — موجودی
  فعلی هر کالا در هر انبار (هر جفت انبار+کالا فقط یک ردیف دارد، quantity
  در همان ردیف آپدیت می‌شود)
- **Transactions**: timestamp, type(IN/OUT/TRANSFER), warehouse_name,
  item_name, quantity, ref_warehouse, note — لاگ append-only همه‌ی حرکات،
  هرگز ویرایش یا حذف نمی‌شود (تاریخچه‌ی قابل اعتماد)
- **PurchaseRequests**: timestamp, warehouse_name, item_name,
  quantity_requested, status(pending/...), note

## منطق کلیدی
- **ثبت ورود (stock-in)**: اگر ردیف انبار+کالا در Stock وجود نداشته باشد
  ساخته می‌شود، وگرنه quantity آن جمع می‌شود. یک ردیف IN به Transactions
  اضافه می‌شود.
- **ثبت خروج (stock-out)**: اگر موجودی کافی نباشد خطا می‌دهد (موجودی منفی
  مجاز نیست). یک ردیف OUT به Transactions اضافه می‌شود.
- **انتقال بین انبارها (transfer)**: معادل یک stock-out از مبدا + یک
  stock-in در مقصد، با یک ردیف TRANSFER در Transactions که هم مبدا هم
  مقصد (ref_warehouse) در آن ثبت می‌شود.
- **جستجوی کالا (check)**: تطبیق substring (case-insensitive) روی نام
  کالا در تب Stock، نتایج از همه‌ی انبارها نشان داده می‌شود.
- **گزارش موجودی کم (low-stock)**: مقایسه quantity در Stock با min_stock
  در Items؛ فقط کالاهایی که min_stock>0 دارند بررسی می‌شوند.
- **درخواست خرید (request-purchase)**: قبل از ثبت، تمام انبارهای دیگر را
  برای همان کالا چک می‌کند. اگر در جای دیگری موجود بود، درخواست ثبت
  نمی‌شود و به‌جایش انتقال داخلی پیشنهاد می‌شود — مگر اینکه با `--force`
  دوباره اجرا شود (مثلاً وقتی موجودی انبار دیگر هم کافی نیست یا کیفیت
  مناسب نیست).

## نکات و محدودیت‌ها
- Service Account فقط Scope «spreadsheets» دارد (نه Drive)؛ بنابراین این
  ابزار نمی‌تواند شیت جدید بسازد یا شیت‌ها را بر اساس نام پیدا کند — همیشه
  با `INVENTORY_SPREADSHEET_ID` مشخص کار می‌کند. این تصمیم آگاهانه است تا
  نیازی به فعال‌سازی Drive API نباشد.
- نام کالا و نام انبار کلید تطبیق هستند (case-insensitive، با trim فاصله)؛
  اگر یک کالا با دو املای متفاوت ثبت شود (مثلاً «پیچ ۸» و «پیچ 8»)، سیستم
  آن‌ها را دو کالای جدا می‌بیند. تا وقتی نیاز واقعی پیش نیامده، normalize
  پیچیده‌تر (fuzzy matching) اضافه نشده است.
- quantity می‌تواند اعشاری باشد (برای کالاهایی مثل متر کابل)؛ نوع داده
  `float` است.

## تست شده
- CLI پایتون (`tools/inventory.py`): setup، add-warehouse، add-item،
  stock-in، stock-out، transfer، check، low-stock، request-purchase همه با
  داده‌ی واقعی روی شیت تست شدند و کار می‌کنند ✅
- Apps Script API (`webapp/Code.gs`) و وب‌سایت GitHub Pages: تمام صفحات
  (200 OK) و endpoint اصلی (`?action=warehouses`) تست شدند ✅

## معماری اپ وب (نسخه‌ی دوم — جایگزین HtmlService اولیه)
نسخه‌ی اول با HtmlService خود Apps Script ساخته شده بود، اما محدودیت ظاهری و
سرعتی iframe sandbox آن قابل قبول نبود. معماری فعلی:

- **بک‌اند (API)**: `webapp/Code.gs`، یک اسکریپت Bound به همان شیت موجودی،
  دیپلوی‌شده به‌عنوان Web App. تمام عملیات (خواندن و نوشتن) فقط با درخواست
  GET و پارامتر `action` انجام می‌شود (نه doPost) — چون Apps Script به
  درخواست‌های OPTIONS (CORS preflight) پاسخ نمی‌دهد و GET ساده این مشکل را
  ندارد. خروجی همیشه JSON با `{success, data}` یا `{success:false, error}`.
  دقیقاً همان الگوی `GAS_URL?action=list&...` که در پروژه‌ی
  `telegram daily workshop` استفاده شده.
- **فرانت‌اند**: `docs/` (روی شاخه‌ی main, مسیر `/docs`) — سه صفحه‌ی استاتیک
  (`index.html`, `workshop.html`, `admin.html`) + `assets/style.css` و
  `assets/app.js` مشترک. هاست‌شده روی **GitHub Pages**، ریپوی
  `Imanskat/workshop-inventory-app` (Public).
  - آدرس زنده: https://imanskat.github.io/workshop-inventory-app/
  - `assets/app.js` ثابت `API_BASE` را به آدرس Deploy شده‌ی Apps Script
    اشاره می‌دهد.
- **دیپلوی Apps Script** با `clasp` (نه کپی-پیست دستی): پروژه‌ی Apps Script
  با `clasp create --type standalone --parentId <SPREADSHEET_ID>` به شیت
  Bound شد (نکته: `--type sheets` به‌اشتباه شیت جدید می‌سازد؛ باید
  `standalone` + parentId شیت موجود باشد). تغییرات بعدی با
  `clasp push` و `clasp deploy -i <deploymentId>` (همان دیپلویمنت آی‌دی، تا
  لینک API ثابت بماند) اعمال می‌شود.
- **نکته‌ی الزامی یک‌باره**: بعد از اولین push/deploy، باید مالک اسکریپت
  (همان اکانتی که با `clasp login` وارد شده) یک‌بار از ادیتور Apps Script
  (script.google.com) یک تابع (مثلاً `listWarehouses`) را دستی Run کند و
  Authorization را Allow کند — وگرنه حتی با `access: ANYONE_ANONYMOUS`،
  درخواست‌های عمومی ۴۰۳ می‌گیرند (اسکریپت هنوز هیچ‌وقت برای دسترسی به شیت
  مجوز نگرفته).

### ⚠️ ریسک امنیتی پذیرفته‌شده
لینک API (`API_BASE` در `assets/app.js`) با `access: ANYONE_ANONYMOUS`
دیپلوی شده و این فایل در ریپوی **عمومی** گیت‌هاب است — یعنی هرکسی که سورس
رو ببیند می‌تواند بدون رمز موجودی را تغییر دهد، نه فقط کسانی که لینک اپ را
از طرف ما گرفته‌اند. کاربر این ریسک را آگاهانه برای شروع پذیرفته (تصمیم
2026-06-28). قدم بعدی پیشنهادی برای رفع این مشکل: اضافه کردن یک `token`
ساده به همه‌ی درخواست‌ها که در Apps Script Properties بررسی شود (نه در
سورس عمومی) — هنوز ساخته نشده.

### نکته نگه‌داری
هر تغییری در منطق کسب‌وکار (مثلاً قوانین چک قبل از خرید) باید همزمان هم در
`tools/inventory.py` هم در `webapp/Code.gs` اعمال شود — این دو مستقل از هم
به یک منطق مشابه روی یک شیت پیاده‌سازی شده‌اند، کد مشترک ندارند.

## باقی‌مانده / مراحل بعدی پیشنهادی (نیاز به تأیید کاربر قبل از ساخت)
- رمز/توکن ساده برای endpoint های نوشتنی (رفع ریسک امنیتی بالا)
- هشدار خودکار موجودی کم (مثلاً تلگرام، مشابه `telegram daily workshop`)
- پیش‌بینی مصرف بر اساس تاریخچه‌ی Transactions
- مدیریت امانت/جابجایی ابزار (که برمی‌گردد، برخلاف مواد مصرفی)
- مقایسه قیمت/تامین‌کننده قبلی هنگام خرید واقعی
