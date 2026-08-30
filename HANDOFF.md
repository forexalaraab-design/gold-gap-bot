# توثيق المشروع — بوت تداول الفجوات بين سعر الذهب العالمي وسعر منصة FP Markets

هذا المستند أُنشئ لضمان انتقال سلس لأي وكيل ذكاء اصطناعي أو مبرمج جديد.
اقرأه كاملاً قبل أي تعديل، وثبّت من «الحالة الحالية» و«الخطوات التالية» قبل الكتابة.

---

## 1) الهدف النهائي للمشروع

بناء **بوت تداول آلي بالبايثون** يعمل على استراتيجية الفروقات/الفجوات بين:

- **سعر الذهب العالمي** (XAU/USD الفوري من مصدر مجاني)
- **سعر الذهب داخل منصة الوسيط** (FP Markets عبر cTrader Open API)

الفكرة: عندما تتسع الفجوة (gap) عن حد معين، يفتح البوت صفقة رهاناً بعودة الفجوة إلى متوسطها (Mean Reversion)، مع SL/TP وإدارة مخاطر.

### القيود الصارمة التي اتفقنا عليها مع المالك
| الشرط | المعنى |
|---|---|
| مجاني بالكامل | بلا رسوم استضافة/برامج/بيانات مدفوعة |
| بلا بطاقة ائتمان | لا يعتمد على AWS/VPS التي تتطلب بطاقة |
| بلا RDP | لا سطح مكتب بعيد |
| بلا جهاز يعمل دائماً | البوت يعمل بالجدولة على GitHub Actions (مجاني) ثم ينام |
| مع تحذير شفاف | هذه الاستراتيجية ليست أربيت راج مضموناً؛ رهان على عودة الفجوة |

---

## 2) القرارات التي اتخذناها (سجل الاختيارات)

| القرار | الاختيار | السبب |
|---|---|---|
| بنية التنفيذ | **cTrader Open API** (وليس MT4/MT5) | REST/Protobuf من السحابة، بلا منصة ولا RDP |
| الوسيط | **FP Markets** | ECN حقيقي، يدعم Open API، إيداع أدنى $100، تنظيم ASIC/CySEC |
| الاستضافة | **GitHub Actions** (جدولة) | مجاني بلا بطاقة؛ تحديث دوري كل ~15 دقيقة يكفي لاستراتيجية M15 |
| الهوية | cTrader ID: **mohammadkreich** | هوية Spotware الخاصة بالمستخدم |
| الحساب | **FP Trading – Demo – 1121509 – 1,000$ – 1:500** | أول تشغيل بتجريبي بالضرورة |
| البيئة (ENVIRONMENT) | `"demo"` حالياً | يمكن التحويل إلى `"live"` بعد نجاح التجريبي |

---

## 3) حالة المشروع الحالية (مهم جداً)

### تم إنجازه ✅
1. إنشاء هيكل الملفات (تفاصيل أدناه).
2. بيئة افتراضية `/.venv` مثبتة ومعالَجة التعارضات فيها (تعمل الآن).
3. `py_compile` ناجح لكل السكريبتات.
4. تسجيل تطبيق في openapi.ctrader.com (الاسم: **GoldGapBot**، الحالة Active).
5. ملء `config.py` بقيم Client ID/Secret الحقيقية.
6. امتلاك المالك cTrader ID + ديمو FP Markets (مؤكد من id.ctrader.com).
7. اختبار الشبكة: HTTPS مفتوح ✅، المنفذ 5035 يعمل على `live.ctraderapi.com` ✅،
   لكن **`demo.ctraderapi.com:5035` لم يستجب من شبكة المالك** عند أول محاولة (أعد المحاولة لاحقاً).
8. بدء تدفق الحصول على التوكن لكنه فشل حتى الآن (انظر «العقبة الحالية»).

### الحالة الآن — الاتصال مكتمل بنجاح ✅
- `auth_tool.py` أنتج **`token.json`** بالنجاح (بعد جعل السكريبت يستخرج `code=` من العنوان الملصوق كاملاً).
- `connect_test.py` أكمل **البنية الثلاثية كاملة**:
  ```
  تم الاتصال بالسيرفر: demo.ctraderapi.com | المنفذ: 5035
  الطبقة 1: مصادقة التطبيق تمت بنجاح.
  الطبقة 2: جلب قائمة الحسابات تم بنجاح.
      ctidTraderAccountId=48473755 | mode=demo | login=1121509
  الطبقة 3: مصادقة الحساب تمت بنجاح لحساب: 48473755
  ```
- البيانات المؤكدة من الاستجابة الفعلية:
  - معرّف الحساب الفعلي (ctidTraderAccountId) = **48473755** (login **1121509**).
  - `balance = 100000` أي **1,000$** بمقياس moneyDigits=2، و assetId للعملة = **15** (USD).
  - سيرفر الديمو `demo.ctraderapi.com:5035` **يتقطع أحياناً** (TCP timeout) — أُضيفت إعادة محاولة تلقائية في main.py. إن رجع الفشل لاحقاً، البديل `ENVIRONMENT="live"`.
- **علاج هام:** لا تطبع رموزاً غير ASCII مثل ✅ في السكريبتات لأن الطرفية الافتراضية (cp1256) تفشل أحياناً؛ استخدم نصاً إنجليزياً في السكريبتات، أو شغّل `chcp 65001` قبل التشغيل.

### الحالة الآن — بوت الفجوات مبني ويعمل ✅
- كُتبت `cbot.py` (غلاف cTrader)، `gold_price.py` (سعري الذهب)، `main.py` (البوت)، و`goldgap.yml` (جدولة GitHub Actions).
- **اختبار فعل على الديمو نجح كاملاً:** اتصال → مصادقة → رصيد → رمز XAUUSD (symbolId=41) → سعر فوري → حساب الفجوة → تسجيل في `data/gap_history.csv`.
  ```
  account_id=48473755 | balance=100000 | symbol_id=41 | digits=2
  bid=4456.23  ask=4456.49  platform=4456.36  global=4456.40  gap=-0.04
  ```
- اختبار مسار **فتح/إغلاق صفقة**: الحجم وُجد صحيحاً (0.01 لوت = volume 100) ورسالة الأمر وصلت السيرفر، لكن السيرفر رد `MARKET_CLOSED` لأن الاختبار جرى **يوم الأحد** (سوق الذهب مقفل). إعادة الاختبار ضرورية **أول افتتاح السوق (الأحد 22:00 بالتوقيت العالمي)**.
- `config.MODE="log"` حالياً (تسجيل فقط). التفعيل بـ `"trade"` بعد اكتمال التدفئة (≥5 قياسات) وفتح السوق.

### الخطوات التالية (لأي وكيل جديد)
1. على الديمو: عند افتتاح السوق اختبر فتح/إغلاق صفقة يدوياً (كان `MARKET_CLOSED` في عطلة نهاية الأسبوع).
2. ارفع المشروع إلى **مستودع GitHub عام** وضع الأسرار في Secrets (القيم موجودة في `config.py` و`token.json`).
3. بعد تجميع ≥5 قياسات فجوة وتثبيت s.d. قابلة للاحترام، حوّل `CBOT_MODE=trade` (متغير بيئة في workflow أو config).
4. راقب `data/gap_history.csv` و`data/bot_state.json` في المستودع.

---

## 4) بنية الملفات

```
مجلد جديد (2)/
├── config.py          # الإعدادات: ENVIRONMENT, APP_CLIENT_ID/SECRET, APP_REDIRECT_URI, TOKEN_FILE
├── auth_tool.py       # أداة لمرة واحدة: مصادقة OAuth وتخزين التوكن في token.json
├── connect_test.py    # اختبار الاتصال بثلاث طبقات ويعرض قائمة ctidTraderAccountId
├── bot.py             # (قديم) بوت MT5 — لم يعد ذا صلة، يمكن حذفه أو تجاهله
├── gold_price.py      # جلب السعر العالمي: gold-api.com (أساسي) + Yahoo GC=F (احتياطي)
├── cbot.py            # غلاف cTrader: اتصال/مصادقة/سعر/صفقات (مع فك Protobuf)
├── main.py            # البوت: يجمّع اللغتين، يبني الإحصاء، يقرر، يسجل
├── requirements.txt   # ctrader-open-api >= 0.9.2, requests
├── .gitignore         # يستبعد .venv و __pycache__ و token.json
├── .github/workflows/goldgap.yml  # جدولة كل 5 دقائق على GitHub Actions
├── data/              # gap_history.csv (سجل الفجوات) + bot_state.json (الحالة) — يُرفع للمستودع
├── token.json         # يُنشأ لاحقاً — سري جداً، لا يُرفع أبداً
└── .venv/             # بيئة افتراضية جاهزة تعمل
```

> ملاحظة: `bot.py` كان أول محاولة بوت على MT5 (استراتيجية متوسّطين). تُركت كمرجع لكن **لم تُستخدم** بعد انتقالنا لبنية cTrader.

---

## 5) شرح آلية الربط (3 طبقات) — لمن لم يطلّع بعد

البنك = خوادم cTrader Open API. البوت يثبت هويته ثلاث مرات بالترتيب:

```
طبقة 1: هوية التطبيق (App)   → ProtoOAApplicationAuthReq (clientId + clientSecret)
طبقة 2: هوية المستخدم (أنت)  → رمز وصول AccessToken (كود OAuth حسبتها مسبقاً)
طبقة 3: هوية الحساب          → ctidTraderAccountId + accessToken = قفل البوت على حسابك
```

- كل طلب لاحق (أسعار، صفقات) لا يقبل إلا بعد نجاح الطبقات الثلاث.
- الحصول على AccessToken: رابط مصادقة في المتصفح → تسجيل دخول cTrader ID → موافقة → كود `code=` ← يُستبدل بتوكن في `https://openapi.ctrader.com/apps/token` (سكوب `trading` لصلاحية التداول).

### نقاط الدخول (EndPoints) — مؤكدة من SDK
| | العنوان | المنفذ |
|---|---|---|
| Demo | `demo.ctraderapi.com` | **5035** |
| Live | `live.ctraderapi.com` | **5035** |
| Auth URI (مصادقة المتصفح) | `https://openapi.ctrader.com/apps/auth` | - |
| Token URI (تبادل الكود) | `https://openapi.ctrader.com/apps/token` | - |
| بوابة هوية الحسابات | `https://id.ctrader.com` | - |

---

## 6) مواصفات SDK والرسائل — حقائق تحققت منها فعلياً

المكتبة الرسمية: `ctrader-open-api` (Spotware/OpenApiPy، تعمل بـ Twisted غير متزامن).

- **كل الرسائل في** `ctrader_open_api.messages.OpenApiMessages_pb2`:
  `ProtoOAApplicationAuthReq/Res`, `ProtoOAGetAccountListByAccessTokenReq/Res`,
  `ProtoOAAccountAuthReq/Res`, `ProtoOASymbolsListReq/Res`, `ProtoOAGetTrendbarsReq`,
  `ProtoOANewOrderReq`, `ProtoOAClosePositionReq`, `ProtoOAReconcileReq/Res`.
- استجابة قائمة الحسابات: الحقل هو **`ctidTraderAccount`** (متكرر من نوع
  `ProtoOACtidTraderAccount` في `OpenApiModelMessages_pb2`)، وكل عنصر له:
  `ctidTraderAccountId`, `isLive`, `traderLogin`.
  (لا يوجد حقل اسمه `ctidTraderAccountId` مباشرة في الاستجابة — سبب خطأ سابق وتم إصلاحه).
- **لا يوجد** `ProtoOAGetPositionListReq` في هذه النسخة — لقراءة الصفقات استخدم
  **`ProtoOAReconcileReq`** (يُرجع orders/positions) أو `ProtoOAOrderListReq` — تأكد من حقوله.
- وحدات البيانات (مؤكدة عملياً — **تصلح التصور الشائع**):
  - **كل الردود على الشبكة تأتي مغلفة في `ProtoMessage`** (`payloadType` + `payload` بايتات):
    استخدم `Protobuf.extract(msg)` في كل نقطة استجابة، وإلا ستقرأ حقولاً خاطئة.
  - **الحجوم**: `volume = لوت × lotSize` — و`lotSize` لرمز XAUUSD = **10000** (أي 0.01 لوت = volume **100**).
    لا تستخدم الصيغة المبسطة (لوت × 100) — مفيدة للفوركس فقط.
  - **الأسعار الفورية (spot)**: تأتي بمقياس **10^5** داخلي لـ XAUUSD (قسّم على `SPOT_SCALE=100000`)
    وليس بمقياس `digits` (digits=2 هو دقة العرض فقط). تحقق: bid خام = 445623000 → 4456.23.
  - **الحقول من كائن الرسائل عشوائية نسبياً في هذه النسخة**: بعض `symbolId` بادئة/مكررة
    (`ProtoOASubscribeSpotsReq.symbolId` **repeated**، و`ProtoOASymbolByIdReq.symbolId` **repeated** لعدة رموز!)
    — بـنى بدلاً من kwargs. تحقق من `fields_by_name[x].label` (3 = repeated) قبل البناء.
  - **الزوامن**: مللي ثانية UTC. **الشموع**: `ProtoOATrendbarPeriod.M1` إلخ.
- `client.send(req)` يعيد Deferred يُستدعى عند وصول الرد ذي `clientMsgId` نفسه (يُطابق عبر `ProtoMessage.clientMsgId`).
- يوجد `ProtoOAGetTickDataReq/Res` في هذه النسخة (بيانات الشموع/الأسعار السابقة) — لا حاجة لها الآن لأننا نستخدم البث الفوري via `ProtoOASubscribeSpotsReq`.
- التوكن كائن JSON يحوي: `accessToken`, `refreshToken`, `expiresIn` (≈30 يوماً) — التجديد عبر `Auth.refreshToken`.
- إرسال أمر جديد يُرجع `ProtoOAExecutionEvent` (وليس Res)، ورفضه يُرجع `ProtoOAOrderErrorEvent` —
  تحقق من `errorCode` (جرّبنا `TRADING_BAD_VOLUME` ثم `MARKET_CLOSED` في عطلة الأسبوع).

---

## 7) بوت الفجوات — بُني ويعمل (التصميم المعتمد)

سير العمل عند كل جدولة (كل 5 دقائق على GitHub Actions):
```
1) جلب سعر الذهب العالمي XAU/USD  (gold-api.com أساسي ← Yahoo GC=F احتياطي)
2) جلب سعر XAUUSD من FP Markets    (اشتراك Spots فوري، symbolId=41)
3) gap = سعر المنصة − السعر العالمي  (بالمقياس الصحيح SPOT_SCALE)
4) وضع LOG (افتراضي): يسجل فقط في data/gap_history.csv
5) وضع TRADE (بعد التدفئة ≥5 قياسات): |z| ≥ Z_ENTRY → فتح صفقة (SELL إذا gap>0 / BUY غيره)
6) |z| ≤ Z_EXIT → إغلاق؛ وإلا SL/TP على السيرفر (حد أقصى للخسارة والانحراف)
```

### المعاملات الحالية (config.py — كلها قابلة للتعديل)
| المعامل | القيمة | المعنى |
|---|---|---|
| MODE | `"log"` | `"trade"` عند جاهزية |
| Z_ENTRY / Z_EXIT / Z_STOP | 2.0 / 0.5 / 3.5 | انحرافات معيارية للدخول/الإغلاق/السقف |
| SL_AFTER_ENTRY_USD | 8.0 | أدنى مسافة إيقاف بعد الدخول (≈8% من $100) |
| MAX_ENTRY_GAP_USD | 50.0 | رفض فجوة وهمية/خبرية > 50$ |
| MAX_GAP_USD | 100.0 | حذف القياسات الشاذة من الإحصاء |
| ROLLING_WINDOW / MIN_SAMPLES | 48 / 5 | نافذة المتوسط والانحراف، والحد الأدنى للتدفئة |
| LOT | 0.01 | لعبة $1 لكل $1 حركة |
| MIN_BALANCE_TO_TRADE | 200 | دونها يبقى تسجيلاً فقط |

### تحذيرات صادقة (متفق عليها مع المالك)
- هذه **رهان عودة فجوة (Mean Reversion)** وليست أربيتراجاً مضموناً.
- على $100، صفقة 0.01 ذهب = مخاطرة 5–10% → **بدون تفعيل تداول حي إلا بعد نمو الرصيد**.
- العتبات مبنية إحصائياً من بيانات الفجوة نفسها (زمن تدفئة) لا قيم من الإنترنت.

---

## 8) خطة النشر النهائية

- **تم إنشاء** `.github/workflows/goldgap.yml` بجدولة `*/5 * * * *` + `workflow_dispatch`.
- **تم الإنجاز الفعلي على GitHub:**
  - المستودع العمومي: `https://github.com/forexalaraab-design/gold-gap-bot`
  - أول تشغيل عبر Actions **نجح كاملاً** (run 33330421217):
    اتصال ديمو (48473755، $1000) ← سعر المنصة 4456.36 ← العالمي 4456.40 ← gap=-0.04 ←
    حفظ في `data/gap_history.csv` ← دفع تلقائي (commit `bb48a44`).
  - الأسرار الستة مثبتة في Settings: `CBOT_APP_CLIENT_ID`, `CBOT_APP_CLIENT_SECRET`,
    `CBOT_ACCESS_TOKEN`, `CBOT_REFRESH_TOKEN`, `CBOT_MODE=log`, `CBOT_ENVIRONMENT=demo`.
  - الأسرار الحقيقية ليست في الملفات المرفوعة: `config.py` بلا قيم (يقرأ env) و
    `config_local.py` (قيم حقيقية) و`token.json` في `.gitignore`.
  - انتبه: لتجنّب كشف السر، لا ترفع `config_local.py` أبداً؛ وعند تجديد `token.json`
    حدّث سر `CBOT_ACCESS_TOKEN`/`CBOT_REFRESH_TOKEN`.
- متبقٍ بعد النشر:
  1. إن أظهر GitHub إشعار "scheduled workflows disabled" فعّل الجدولة من
     Settings → Actions → General (أول مرة فقط).
  2. اختبار فتح/إغلاق الصفقة على الديمو **أول افتتاح السوق** (كان `MARKET_CLOSED` يوم الأحد):
     `$env:CBOT_MODE='trade'; python main.py` (من المجلد المحلي).
  3. بعد تدفئة كافية والتحقق من تباين الفجوة لدى السوق، حوّل سر `CBOT_MODE` إلى `trade`.

---

## 9) أسرار وأمن (لا تُتجاهل)

- `config.py` يحتوي Client ID/Secret الحقيقيين (ملآن من المالك). **تظهر في المحادثة**؛ إنشاؤها غير مكتمل بعد، وينصح بتوليد Secret جديد عند النشر.
- `token.json` = مفتاح الدخول الكامل → **ممنوع رفعه/مشاركته**.
- المالك مبتدئ — اشرح الخطوات بأسلوب واضح بالعربية، وكل خطوة تنتظر تأكيده.

---

## 10) ملاحظات تقنّية مهمة مكتشفة أثناء العمل

- منفذ الصنف الدّرعي للـ cTrader OpenAPI هو **5035** وليس 5030 (حقيقة من endpoints.py).
- تعارض المكتبات: `pyopenssl` يتطلب `cryptography<43` بينما `service-identity` يتطلب `>=47` —
  الحل الناجح: تثبيت الكل دفعة واحدة بلا تقييد، أو نمبر إصدار متوافق. **لا تعيد تشغيل pip عشوائياً**
- الحروف العربية قد تُعرض مشوهة في الكونسول → شغّل `chcp 65001` قبل الأوامر أو `$env:PYTHONIOENCODING='utf-8'`.
- `demo.ctraderapi.com` لم يستجب من شبكة المالك وقت أول اختبار رغم أن `live` استجاب؛ **ثم استجاب الديمو لاحقاً ونجح الاتصال كاملاً عليه** (لقطة غيّرت نتيجتها). إن عاد الفشل → بدّل `ENVIRONMENT="live"`.

---

## 11) روابط مرجعية رسمية

- لوحة تطبيقات Open API: `https://openapi.ctrader.com`
- بوابة ال cTrader ID والتحقق من الحسابات: `https://id.ctrader.com`
- توثيق سكوب: `https://help.ctrader.com/open-api/python-SDK/python-sdk-index/`
- مصادقة الحسابات: `https://help.ctrader.com/open-api/account-authentication/`
- كود المصدَر (OpenApiPy): `https://github.com/spotware/OpenApiPy`
- أمثلة (ConsoleSample): `https://github.com/spotware/OpenApiPy/tree/main/samples/ConsoleSample`