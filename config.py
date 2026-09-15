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
# عتبة حجم الزخم (بالدولار) قبل اعتبار الإشارة قوية — من ملاحظة أن
# الحركات ≥1.5$ هي الأكثر استمرارية، نطلب عتبة أدنى قليلاً لضمان
# تكرار مقبول مع جودة دخول أعلى من فقط ≥1.5.
MOMENTUM_MIN_USD = _env_float("STRAT_MOMENTUM_MIN", 1.20)
# حارس شذوذ السعر: إذا تحرك سعر المنصة أكثر من هذا القدر خلال نافذة
# الزخم (~80 ثانية) فهذا خلل شريط/سيولة — نغلق. قفزة ≥ 6$ في 80 ثانية
# تكاد مستحيلة في XAUUSD السائل؛ القيمة مبنية على ملاحظة أن أكبر حركة
# طبيعية ≈ 0.9$/دقيقة.
PRICE_JUMP_ANOMALY_USD = _env_float("STRAT_PRICE_JUMP_ANOMALY", 6.0)

# SL_AFTER_ENTRY_USD: المسافة الدنيا لوقف الخسارة بعد الفتح (بالفجوة/الوحدات).
# عند 0.01 لوت (نقطة=$1) خُفّض من 3.0 إلى 2.5: مخاطرة أصغر ≈ $2.5/صفقة (طلب المستخدم).
SL_AFTER_ENTRY_USD = _env_float("STRAT_SL_USD", 2.5)

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
# 5.0 → 3.0: عدد أقل لكنه لا يزال واقعيًا.
COOLDOWN_MINUTES = _env_float("STRAT_COOLDOWN_MIN", 3.0)

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
# أُنصف (1.50 → 0.75) موازنة لخفض اللوت.
TRAILING_ARM_USD = _env_float("STRAT_TRAILING_ARM", 0.75)

# TRAILING_BACK_USD: إذا تراجع الربح من ذروته بهذا المقدار، نغلق الصفقة.
# أُنصف (0.60 → 0.30) موازنة لخفض اللوت.
TRAILING_BACK_USD = _env_float("STRAT_TRAILING_BACK", 0.30)

# MAX_HOLD_HOURS: أقصى وقت للحفاظ على الصفقة مفتوحة قبل الإغلاق الإلزامي.
# 2.0 → 4.0: وقت أطول قليلاً لإعطاء الفرصة للاستعادة، لكن نغلق في النهاية.
MAX_HOLD_HOURS = _env_float("STRAT_MAX_HOLD_HOURS", 2.5)

# الحد الأقصى للخسارة لصفقة واحدة (إغلاق آلي).
# 6.0 → 3.0: أُنصف مع خفض اللوت (3 نقاط سعر = 3$) — مخاطرة أقل لكل صفقة.
MAX_LOSS_USD = _env_float("STRAT_MAX_LOSS_USD", 3.0)

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
HUMAN_SKIP_SIGNAL_PROB = _env_float("STRAT_HUMAN_SKIP", 0.12)
HUMAN_POLL_JITTER_SEC = _env_float("STRAT_HUMAN_POLL_JITTER", 1.0)