import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_float(name, default):
    try:
        return float(os.environ.get(name)) if os.environ.get(name) else default
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ===== cTrader / FP Markets =====
ENVIRONMENT = os.environ.get("CBOT_ENVIRONMENT", "demo")  # demo | live
APP_CLIENT_ID = os.environ.get("CBOT_APP_CLIENT_ID", "")
APP_CLIENT_SECRET = os.environ.get("CBOT_APP_CLIENT_SECRET", "")
APP_REDIRECT_URI = "http://localhost/callback"

# Local-only overrides (real credentials live here, NOT committed to git)
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass

# Token: prefer env (GitHub Actions secrets), else token.json
CBOT_ACCESS_TOKEN = os.environ.get("CBOT_ACCESS_TOKEN", "")
CBOT_REFRESH_TOKEN = os.environ.get("CBOT_REFRESH_TOKEN", "")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
TOKEN_STORE = os.environ.get("CBOT_TOKEN_STORE", TOKEN_FILE)

# ===== Global gold sources =====
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
YAHOO_OFFSET_USD = 0.0  # GC=F is futures; add offset to approximate spot if needed

# ===== Signal & risk (units: USD per ounce unless stated) =====
SYMBOL = "XAUUSD"

# الحجم: 0.01 لوت ثابت فقط (ممنوع تغييره من env أو أي مصدر)
# خُفّض من 0.02 إلى 0.01 لخفض المخاطرة لكل صفقة لنصفها (طلب المستخدم:
# "اللوت عالي"). عند 0.01 لوت = 100 وحدة → 1 نقطة سعر = $1.
LOT = 0.01

# cTrader delivers spot prices for XAUUSD scaled by 10**5 internally
SPOT_SCALE = 100000.0

# وحدة السعر في أوامر SL/TP عبر الـ API: الرمز digits=2 → السعر بالدولار ×100.
# (أوامر الفتح بتوقفات مقيّسة بـ SPOT_SCALE كانت تُرفض بـ TRADING_BAD_STOPS؛
#  الواجهة اليدوية الناجحة تستخدم هذه الوحدة.)
PRICE_UNIT = 100.0

# Modes: "log" = record gaps only; "trade" = open/close demo positions
MODE = os.environ.get("CBOT_MODE", "trade")  # trade = نفّذ صفقات حقيقية

# Self-built thresholds (statistical), replaced by measured scale after warmup.
# Z_ENTRY: الحد الأدنى لـ |z| قبل الدخول. كلما زاد الرقم، قلّت الدخولات الخاطئة.
# 1.5 → 2.0: نزيد الدقة، نقلل الدخول الخاطئ، نعتمد إشارات أقوى فقط.
Z_ENTRY = _env_float("STRAT_Z_ENTRY", 2.0)

# Z_ENTRY_SOFT: مستوى ثاني أقل — دخول إذا |z| ≥ Z_ENTRY_SOFT مع شروط إضافية
# (مثلاً: الفجوة واضحة والسرعة غير خطرة). 1.2 → 1.5: رفع جودة الدخول
# لتقليل نقاط الدخول الفاشلة (طلب المستخدم).
Z_ENTRY_SOFT = _env_float("STRAT_Z_ENTRY_SOFT", 1.5)

# Z_EXIT: إغلاق إذا عاد |z| إلى هذا المستوى (عندما يتراجع الانحراف).
Z_EXIT = _env_float("STRAT_Z_EXIT", 0.5)

# Z_STOP: حدود上限 لـ |z| قبل اعتباره خطرًا أو غير مستدام.
Z_STOP = _env_float("STRAT_Z_STOP", 3.5)

# ===== إشارة الدخول: زخم سعر المنصة (مفهوم "لحاق المنصة" 2026-09-14) =====
# التحليل: زخم mid يستمر (بعد صعود≥1.5$ يكمل صعوداً 87% بمتوسط +2.74$،
# وبعد هبوط≤-1.5$ يكمل 74%)، بينما المصدر العالمي لا يتنبأ بالمنصة.
# لذلك الدخول يُحدد باتجاه زخم سعر المنصة (platform_momentum)، وليس
# بالفجوة ولا z-score على mid ولا المصدر الخارجي.
# MOMENTUM_ON: تفعيل/تعطيل إشارة الزخم للدخول.
MOMENTUM_ON = os.environ.get("STRAT_MOMENTUM_ON", "1") == "1"
# نافذة الزخم بالعينات (كل عينة ~4 ثوانٍ) → ~80 ثانية.
MOMENTUM_WINDOW_ROWS = int(_env_float("STRAT_MOMENTUM_WINDOW", 24))
# عتبة حجم الزخم (بالدولار) قبل اعتبار الإشارة قوية. 2026-09-16:
# 1.20 → 1.50 (دخولات أقل أوثق). 2026-09-23 (طلب صريح بالمزيد من
# الصفقات الهجومية): 1.50 → 1.20 مع بقاء بنود الجودة كاملة
# (تأكيد الدورتين + التوافق الاتجاهي + تغطية التكلفة) — نقاط دخول
# قوية بتردد أعلى. يعود 1.50 فوراً ببند واحد عند الرغبة.
MOMENTUM_MIN_USD = _env_float("STRAT_MOMENTUM_MIN", 1.20)
# حارس شذوذ السعر: إذا تحرك سعر المنصة أكثر من هذا القدر خلال نافذة
# الزخم (~80 ثانية) فهذا خلل شريط/سيولة — نغلق. قفزة ≥ 6$ في 80 ثانية
# تكاد مستحيلة في XAUUSD السائل؛ القيمة مبنية على ملاحظة أن أكبر حركة
# طبيعية ≈ 0.9$/دقيقة.
PRICE_JUMP_ANOMALY_USD = _env_float("STRAT_PRICE_JUMP_ANOMALY", 6.0)

# SL_AFTER_ENTRY_USD: مسافة وقف الخسارة على السيرفر من لحظة الفتح.
# 2026-09-16: 2.5 → 2.0 (طلب المستخدم: ضمان أضيق للستوب). الخسارة
# المحققة ≈ 2.0 + السبريد + العمولة + انزلاق ≈ 2.2–2.4$ — بوبق أسفل
# MAX_LOSS_USD. يجمع وقف السيرفر أولاً ثم يبقى الديناميكي خلفية (الفعلي،
# بعد 2026-09-22 يساوي 2.0 — لأن السيرفر لا ينفّذ مسافة 2.0 للذهب).
SL_AFTER_ENTRY_USD = _env_float("STRAT_SL_USD", 2.0)

# MAX_ENTRY_GAP_USD: إذا ابتعد سعر المنصة عن السعر الخارجي (global) بهذا
# المقدار الكبير جداً، نغلق كحارس أمان (خلل بيانات/سيولة شاذة). لم يعد
# شرط دخول — الدخول يُحدد الآن بانحراف سعر المنصة عن وسطه (z-score على mid).
MAX_ENTRY_GAP_USD = _env_float("STRAT_MAX_ENTRY_GAP", 22.0)

# MIN_GAP_USD: لم يعد شرط دخول (كان دخولاً على الفجوة فقط). تُركت القيمة
# للرصد/السجلات وكمؤشر في لوغ الصفقات. إشارة الدخول الحقيقية = z-score على mid.

# FLTR ضوضاء السوق: لا تدخل صفقة إلا إذا كانت الفجوة ≥ قيمة واضحة
# 0.50 → 1.00: نزيد عتبة الدخول لتقليل الدخول في تذبذبات صغيرة.
MIN_GAP_USD = _env_float("STRAT_MIN_GAP", 1.50)  # جودة أعلى: فجوة أعمق = فرصة أنظف (رفعت من 1.20)

# COOLDOWN_MINUTES: انتظار بعد إغلاق صفقة قبل فتح أخرى (تجنب المتتابعات الخاطئة).
# 5.0 → 3.0 → 1.0 (2026-09-23، طلب صريح: أكثر صفقات هجومية). يتبقى
# التشتت البشري ±15% مطبقاً وقت التنفيذ فلا يبدو ثابتاً بالثانية.
COOLDOWN_MINUTES = _env_float("STRAT_COOLDOWN_MIN", 1.0)

# MAX_TRADES_PER_DAY: الحد الأقصى لعدد الصفقات في اليوم.
# مرفوع عالياً جداً لتعطيل هذا القيد عملياً — الحماية الفعلية هي
# MAX_DAILY_LOSS_USD (توقف الخسارة اليومية).
MAX_TRADES_PER_DAY = int(_env_float("STRAT_MAX_TRADES_PER_DAY", 99999))

FORCE_TEST_OPEN = _env_bool("STRAT_FORCE_TEST_OPEN", False)

TRADING_FEES_PER_TRADE_LOT = _env_float("STRAT_FEES_PER_LOT", 8.0)
# ===== اكتشاف العمولة والسبريد تلقائياً (2026-09-15) =====
# السبريد يُقيس حياً كل دورة من (ask - bid) على cTrader — لا تقدير ثابت.
# العمولة تُقرأ من كائن الصفقة (pos.commission) إن كانت متاحة، وإلا
# تُقدَّر من TRADING_FEES_PER_TRADE_LOT (عمولة لكل لوت) وتُعيَّر عبر
# متوسط العمولة الفعلية المسجلة من الصفقات المغلقة.
# التكلفة الكلية (سبريد + عمولة) تُقيد من كل قرار: الدخول (فلكي يظل
# |catch_up| > العتبة والتكلفة)، والإغلاق (net PnL يعكسها دائماً).
SPREAD_GUARD_USD = _env_float("STRAT_SPREAD_GUARD", 0.80)
COMMISSION_MIN_USD = _env_float("STRAT_COMMISSION_MIN", 0.05)
# منع الدخول إذا فاق السبريد هذا الحد (تذبذب لحظي خارجي / سيولة شاذة).
DYNAMIC_PROFIT_FLOOR_USD = _env_float("STRAT_PROFIT_FLOOR", 2.0)
PROFIT_FLOOR_PER_OLOT_USD = _env_float("STRAT_PROFIT_FLOOR_LOT", 0.2)

# تثبيت الأرباح: إغلاق فوري عند بلوغ ربح صافي محدد
# 3.15 → 1.60: أُنصف لأن اللوت أصبح 0.01 (نقطة=$1) للحفاظ على نفس
# المسافة بالنقاط (~1.6 نقطة) دون المطالبة بحركة سعر أكبر.
PROFIT_TARGET_USD = _env_float("STRAT_PROFIT_TARGET", 1.60)

# TRAILING_ARM_USD: تتبع الأرباح يبدأ عندما يصل الـ PnL الصافي إلى هذه القيمة.
# 2026-09-16 (نظام الإغلاق الجديد): 0.75 → 1.40 — التريلنج يحمي الفائض فوق
# الهدف (TP سيرفر ≈ 1.40) ولا يقطع الأرباح الصاعدة قبل بلوغه.
TRAILING_ARM_USD = _env_float("STRAT_TRAILING_ARM", 1.40)

# TRAILING_BACK_USD: إذا تراجع الربح من ذروته بهذا المقدار نغلق الصفقة.
# 2026-09-16: 0.30 → 0.45 — يرتخي قليلاً كي لا يُقطع بقعة سعرية عابرة.
TRAILING_BACK_USD = _env_float("STRAT_TRAILING_BACK", 0.45)

# NO_PROGRESS_* (2026-09-21 — معالجة الصفقات الخاسرة): صفقة لم تبلغ
# أي ربح (ذروة < NO_PROGRESS_PEAK_USD) وما تزال خاسرة بعد
# NO_PROGRESS_AFTER_SEC من الفتح هي صفقة "ميتة" — الركوب بها نحو
# -3.0 إهدار. نخرجها مبكراً (سبب no_progress) دون أن نمس المتداولات
# الرابحة (أغلبها تنتهي خلال 3-4 دقائق).
NO_PROGRESS_AFTER_SEC = _env_float("STRAT_NO_PROGRESS_AFTER_SEC", 300)
NO_PROGRESS_PEAK_USD = _env_float("STRAT_NO_PROGRESS_PEAK", 0.30)
NO_PROGRESS_MAX_LOSS_USD = _env_float("STRAT_NO_PROGRESS_MAX_LOSS", 0.45)

# SAME_SIDE_LOSS_GUARD_MIN (2026-09-21): بعد خسارة مغلقة لا نعيد الدخول
# بنفس الاتجاه خلال هذه النافذة إلا إذا كانت الإشارة الجديدة أقوى بكثير
# (ضرب SAME_SIDE_LOSS_STRONG_MULT من العتبة). اليوم 33/34 صفقة بنفس
# الجهة وأغلب الخسائر محاولات متتابعة ميتة — هذا القاطع يفضّ تلك الدورات.
SAME_SIDE_LOSS_GUARD_MIN = _env_float("STRAT_SAME_SIDE_LOSS_GUARD_MIN", 40.0)
SAME_SIDE_LOSS_STRONG_MULT = _env_float("STRAT_SAME_SIDE_STRONG_MULT", 1.6)

# GIVEBACK_* (2026-09-22 — حماية التراجع بعد القمة): صفقة بلغت ربحاً
# حقيقياً (قمة ≥ GIVEBACK_ARM_USD) ثم انعكست إلى خسارة (≤ -GIVEBACK_TRIGGER)
# تُغلق فوراً — لا نسمح بتحوّل الربح المحقق إلى خسارة كاملة عند -3.0.
# من تاريخ 200 صفقة: 15 خسارة بلغت قمة +0.5..+1.2 ثم انعكست إلى
# -3.28 متوسط (ضياع -49$). هذه الطبقة تحوّلها إلى خروج ~-0.4..-0.6.
GIVEBACK_ARM_USD = _env_float("STRAT_GIVEBACK_ARM", 0.60)
GIVEBACK_TRIGGER_USD = _env_float("STRAT_GIVEBACK_TRIGGER", 0.40)

# MAX_HOLD_HOURS: أقصى وقت للحفاظ على الصفقة مفتوحة قبل الإغلاق الإلزامي.
# 2026-09-16: 2.5 → 1.0 — خلفية (backstop) أضيق شكلاً مع القاعدة الجذرية
# "لا صفقة بلا وقوف سيرفر": الحماية الأساسية من السيرفر (SL/TP عند الفتح)،
# وهذا العداد سقف إضافي إن فشلت التغطية أو راوح السعر بينهما.
MAX_HOLD_HOURS = _env_float("STRAT_MAX_HOLD_HOURS", 1.0)

# الحد الأقصى للخسارة لصفقة واحدة (إغلاق آلي).
# 6.0 → 3.0: أُنصف مع خفض اللوت (3 نقاط سعر = 3$) — مخاطرة أقل لكل صفقة.
# 2026-09-22: 3.0 → 2.0 — القطع البرمجي هو المتحكم الفعلي (ستوب السيرفر 2.0
# لا يُنفَّذ على أرض الواقع؛ الخسائر المحققة كانت -3.0..-3.4). سجل 200 صفقة:
# -49.94 @3.0 → +24.06 @2.0 بلا أي خفض لعدد الصفقات؛ نقطة تعادل 61% عند 62%.
MAX_LOSS_USD = _env_float("STRAT_MAX_LOSS_USD", 2.0)

# الحد اليومي للخسارة (دائرة أمان).
# مرفوع عالياً جداً عملياً لتعطيل التوقف اليومي (طلب المستخدم: لا
# أمان/عداد خسائر — التداول مستمر دائماً). القيمة الفعلية ممنوعة فقط
# في الخسارة الكارثية النادرة جداً.
MAX_DAILY_LOSS_USD = _env_float("STRAT_MAX_DAILY_LOSS_USD", 99999.0)

# أقصى عدد من الخسائر المتتالية قبل التوقف (دائرة أمان).
# مرفوع عالياً جداً عملياً لتعطيل العداد (طلب المستخدم).
MAX_CONSECUTIVE_LOSSES = int(_env_float("STRAT_MAX_CONSEC_LOSSES", 99999.0))

SESSION_GUARD = os.environ.get("STRAT_SESSION_GUARD", "1") == "1"
LIVE_TRADING_START_HOUR = _env_float("STRAT_SESSION_START", 22.0)
LIVE_TRADING_END_HOUR = _env_float("STRAT_SESSION_END", 5.0)

# فلترة جودة الجلسة: تحليل الصفقات أظهر أن نافذة 16:00–22:00 UTC
# (إغلاق لندن والانتقال) أسوأ نافذة (نسبة فوز 56% وتكبد معظم الخسائر)،
# بينما 22:00–05:00 (80%) و09:00–16:00 (100%) الأفضل — ويوافقه البحث
# (12:30–16:00 ذروة السيولة وأضيق السبريد، و21:00–22:00 تسوية تقتل).
# فعّال افتراضياً؛ يُعطَّل بالـ env التالي.
SESSION_BLOCK_ON = os.environ.get("STRAT_SESSION_BLOCK_ON", "0") == "1"
SESSION_BLOCK_START_HOUR = _env_float("STRAT_SESSION_BLOCK_START", 16.0)
SESSION_BLOCK_END_HOUR = _env_float("STRAT_SESSION_BLOCK_END", 22.0)

# ملاحظة: MAX_GAP_VELOCITY أُلغي (02/02) — الحارس يستخدم الآن
# PRICE_JUMP_ANOMALY_USD على platform_momentum، وحركة الذهب الطبيعية
# (0.5-1$/دقيقة) لا تُشغّل النظام الجديد (6$ في ~80 ثانية = خلل بيانات).

# فلتر الاتجاه القوي: في أيام الاتجاه (هبوط/صعود متواصل) يكون الذهب
# خارج نطاق الارتداد، والدخول ضده = خسائر متتالية. نمنع الدخول إذا
# تحرك سعر المرجع (global) بشكل ثابت في اتجاه مكافئ لـ mini-trend
# يتجاوز الحد بالدولار/دقيقة خلال نافذة حديثة (قيمة متحفظة: يوم
# 2026-09-14 خسر -57$ في 6 max_loss لأن الاتجاه كان ~0.25$/دقيقة).
TREND_ON = os.environ.get("STRAT_TREND_ON", "1") == "1"
# نافذة 300 صف (~20 دقيقة): طويلة بما يكفي لتخفيف الضجيج اللحظي، وقصيرة
# بما يكفي لالتقاط الانهيارات الحادة الحديثة (مثل 18:46 في 2026-09-14
# حيث هبط ~0.94$/دقيقة وسبب -6.02$ مع نافذة 60 دقيقة التي خفّفت الانخفاض
# إلى أقل من العتبة). النافذة القصيرة سابقاً (150/~10 د) كانت تضخم الضجيج.
TREND_WINDOW_ROWS = int(_env_float("STRAT_TREND_WINDOW", 300))
# عتبة 0.55$/دقيقة على نافذة 20 د: تمنع الدخول ضد الانحدارات الحادة
# الراسخة، بينما يظل التداول ممكناً في الحركة الجانبية/الأفقية العادية
# (الذهبي يتحرك طبيعياً 0.19-0.45$ على نافذة 60 دقيقة = أقل ضوضاءً هنا).
TREND_MAX_SLOPE_USD = _env_float("STRAT_TREND_SLOPE", 0.55)
USE_MAD = os.environ.get("STRAT_USE_MAD", "1") == "1"

# Stats (إشارة الدخول الآن على انحراف سعر المنصة mid-About متوسطه — وليس الفجوة)
ROLLING_WINDOW = int(_env_float("STRAT_WINDOW", 48))
MIN_SAMPLES = int(_env_float("STRAT_MIN_SAMPLES", 8))
MIN_BALANCE_TO_TRADE = 200.0
# نطاق معقول لسعر XAUUSD — نستبعد الملاحظات التالفة من الإحصاءات
MIN_PLATFORM_PRICE = 4000.0
MAX_PLATFORM_PRICE = 5000.0

# Files / state
HISTORY_FILE = os.path.join(BASE_DIR, "data", "gap_history.csv")
STATE_FILE = os.path.join(BASE_DIR, "data", "bot_state.json")
TRADES_FILE = os.path.join(BASE_DIR, "data", "trades.csv")
PERF_FILE = os.path.join(BASE_DIR, "data", "performance.json")
MAX_CLOSED_TRADES = 200

# ===== Live loop =====
DURATION_MIN = _env_float("CBOT_DURATION_MIN", 9999.0)  # run until stopped
GLOBAL_POLL_SEC = _env_float("CBOT_GLOBAL_POLL_SEC", 3)
APPEND_EVERY_SEC = 10.0
APPEND_TOLERANCE = 0.02
MAX_HISTORY_ROWS = 2000

# ===== Misc =====
VERSION_REQ = True
CONNECT_TIMEOUT = 30

# ===== إنسانية التنفيذ (HUMANIZATION) — قواعد مرجعية ثابتة =====
# الغرض: ألا يميز البروكر تلقائيَّاً أن الصفقات يديرها بوت (أنماط
# الطلب المنتظمة، الملصقات العشوائية، الحجم الثابت، التوقيت المثالي
# كلها "بصمات" آلية). هذه القواعد تُطبق على كل التحديثات القادمة.
#
# القاعدة 1: لا متطابق في الأوامر — التشتت العشوائي على SL/TP/الحجم
#   ضمن حدودتي آمَن (لا تماس الضمانات).
# القاعدة 2: تأخير بشري قبل الفتح/الإغلاق يعاير به المستخدم (رد فعل).
# القاعدة 3: ملصق-اسم إنساني مقروء (ليس 6 رموز عشوائية آليّة).
# القاعدة 4: أحياناً نُفوّت إشارة صالحة (الإنسان لا يلتقط كل شيء).
# القاعدة 5: زمن حلقة غير صارم (تشتت بسيط في فترة الجرد).
# القاعدة 6: لا نكشف أبداً منطق "الفجوة/القائد-التابع" في أي حقل
#   يُرسل للبروكر (label/comment/clientIds) — لا ذكر لـ yahoo/gap/momentum.
HUMANIZE_ON = _env_bool("STRAT_HUMANIZE_ON", True)
HUMAN_REACTION_SEC_MIN = _env_float("STRAT_HUMAN_REACT_MIN", 2.0)
HUMAN_REACTION_SEC_MAX = _env_float("STRAT_HUMAN_REACT_MAX", 7.0)
HUMAN_SL_TP_JITTER_USD = _env_float("STRAT_HUMAN_SLTP_JITTER", 0.08)
HUMAN_VOLUME_JITTER_FRAC = _env_float("STRAT_HUMAN_VOL_JITTER", 0.05)
# خطوة الحجم الصالحة عند الوسيط بوحدات cTrader (XAUUSD: 1.0 لوت = 10000
# وحدة → 0.01 لوت = 100، والتركيبات الصالحة بمضاعفات 100 فقط). يُكمَّل
# الحجم المُشوش إلى أقرب مضاعف لها حتى لا يرفض الوسيط (TRADING_BAD_VOLUME)
# — عند لوت 0.01 (100) يبقى الحجم كما هو والجتر مدور تلقائياً.
VOLUME_STEP_UNITS = int(_env_float("STRAT_VOLUME_STEP", 100))
# HUMAN_SKIP_SIGNAL_PROB: لقطة "لا أستوعب الصفقة الصغيرة" — تخطي إشارة
# صالحة باحتمال معين. 2026-09-23 (طلب صريح هجومي): خُفّض الافتراضي إلى
# 0 (نلتقط كل إشارة قوية) مع بقاء المفتاح قابلاً للتفعيل عبر env.
HUMAN_SKIP_SIGNAL_PROB = _env_float("STRAT_HUMAN_SKIP", 0.0)
HUMAN_POLL_JITTER_SEC = _env_float("STRAT_HUMAN_POLL_JITTER", 1.0)

# ===== وضع المراقبة (2026-09-23) — إيقاف مؤقت للفتح أثناء إعادة البناء =====
# STRAT_PAUSE_OPEN=1 → لا تُفتح صفقات جديدة أبداً؛ الصفقة القائمة تُدار
# (إغلاق/تريلنج/حدود أمان) كما هي. يُفعَّل من الـ workflow حتى يُسلَّم
# نموذج v2 بعد forward-test ناجح على الديمو.
PAUSE_OPEN = _env_bool("STRAT_PAUSE_OPEN", False)

# ===== نموذج v2 (إعادة البناء 2026-09-23 — فوق نفس البنية) =====
# STRATEGY_MODEL: "v1" = النموذج الحالي (زخم اللحاق مع تأكيد الدورتين)؛
# "v2" = النموذج الجديد المبني على أخطاء 200 صفقة. v2 لا يُفعَّل للحي
# إلا بعد forward-test ناجح على الديمو.
STRATEGY_MODEL = os.environ.get("STRAT_MODEL", "v1").strip().lower()
# STRAT_V2_EVAL: يسجّل قرارات v2 وPnL الافترافي بلا فتح صفقة (بالوازي)،
# في data/v2_virtual.csv للمقارنة مع v1 الحي. مُفعّل افتراضياً فوق v1.
STRAT_V2_EVAL = _env_bool("STRAT_V2_EVAL", True)
# سقف خسارة الصفقة الواحدة في v2 (صافي) — المحقق ≈ القيمة + انزلاق/رسوم.
# 2.0 (v1) → 1.40: الخسائر v1 المحققة فاقت 2.0 (-2.24/-2.75) بسبب
# الانزلاق، فنجعل المحرض أبكر كي يبقى المحقق فعلياً قرب 1.5-1.6.
V2_RISK_PER_TRADE_USD = _env_float("STRAT_V2_RISK", 1.40)
# نسبة الهدف/المخاطرة: TP = max(V2_TP_MIN_USD, RISK * V2_TP_RISK_RATIO).
# الخلل الجوهري في v1: ربح أصغر من الخسارة (R:R < 1). v2 يطالب قراراً
# عكسي (TP ≥ ~2× المخاطرة) ليبقى التوقع إيجابياً عند 40-50% فوز.
V2_TP_RISK_RATIO = _env_float("STRAT_V2_TP_RATIO", 2.0)
V2_TP_MIN_USD = _env_float("STRAT_V2_TP_MIN", 2.0)
# السوق الحي: |زخم المنصة| ≥ هذا الحد وإلا "شريط راكد/سوق ميت" — الدخول
# في سوق متجمد يمدد زمن الحجز ويخسر الثبات (لا حركة للتلاحق).
V2_MIN_PLAT_MOMENTUM = _env_float("STRAT_V2_MIN_PLAT_MOM", 0.40)
# حد الخسارة اليومي في v2 (دائرة أمان حقيقية — يوقف يوم -6$+ بدل
# التسيب المستمر؛ v1 يستخدم 99999).
V2_DAILY_MAX_LOSS_USD = _env_float("STRAT_V2_DAILY_STOP", 6.0)
# غربلة الساعات الموجبة المكتسبة (73% فوز، إيجابية 4/5 أيام):
# 03,06,07,08,10,14,16,17,22,23 UTC — أكبر رافعة فردية لخفض الخسائر
# دون لمس بقية القرارات (كانت خياراً مؤجلاً عند المستخدم).
V2_SESSION_HOURS_ON = _env_bool("STRAT_V2_SESSION_HOURS", True)
V2_POSITIVE_HOURS = (3, 6, 7, 8, 10, 14, 16, 17, 22, 23)
# سبريد أقصى للدخول في v2 — أضيق من v1 (0.80) لضمان تنفيذ نظيف
# (السبريد الواسع يلتهم أول 0.3-0.5$ من أي صفقة).
V2_MAX_SPREAD_USD = _env_float("STRAT_V2_MAX_SPREAD", 0.30)
# سجل التقييم الافتراضي v2
V2_VIRTUAL_FILE = os.path.join(BASE_DIR, "data", "v2_virtual.csv")

# ===== تمويه إنساني أوسع (2026-09-23 — ألا يبدو التنفيذ بوتاً) =====
# 1) تذبذب عتبة الدخول: الفلتر الفعلي لكل دورة = MOMENTUM_MIN ± نسبة
#    (الإنسان لا يثقب حداً حرفياً ثابتاً كل مرة — الأدوات كلها متنوعة).
#    0.10 → 0.03 (2026-09-23، طلب صريح هجومي): تقزيم التذبذب حتى لا
#    يُقصى فعلياً دخول قوي على الخط — يبقى أثراً بصرياً رقيقاً.
HUMAN_ENTRY_JITTER_FRAC = _env_float("STRAT_HUMAN_ENTRY_JITTER", 0.03)
# 2) "انصراف البائع": الاحتمالية أن يقرر المتداول الانصراف/أخذ استراحة
#    عشوائية عوض تنفيذ إشارة صالحة تماماً (فترة ترجيح طويلة 25-90 د) —
#    يكسر إيقاع "أجهز على كل إشارة" نهائياً ويضيف سلوكاً بشرياً واضحاً.
# 2026-09-23 (طلب صريح هجومي): مفعّل = False افتراضياً حتى لا تُهدر
#    إشارة صالحة — الجزء "بشرية" يبقى في الملصقات والتوقيت لا في التضحية
#    بالصفقات. يعود بـ env واحد عند الرغبة في الكسر الإيقاعي.
HUMAN_AWAY_ON = _env_bool("STRAT_HUMAN_AWAY", False)
HUMAN_AWAY_PROB = _env_float("STRAT_HUMAN_AWAY_PROB", 0.08)
HUMAN_AWAY_MIN_MIN = _env_float("STRAT_HUMAN_AWAY_MIN", 25.0)
HUMAN_AWAY_MAX_MIN = _env_float("STRAT_HUMAN_AWAY_MAX", 90.0)