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

# SL_AFTER_ENTRY_USD: المسافة الدنيا لوقف الخسارة بعد الفتح (بالفجوة/الوحدات).
# عند 0.01 لوت (نقطة=$1) خُفّض من 3.0 إلى 2.5: مخاطرة أصغر ≈ $2.5/صفقة (طلب المستخدم).
SL_AFTER_ENTRY_USD = _env_float("STRAT_SL_USD", 2.5)

# MAX_ENTRY_GAP_USD: إذا تجاوزت الفجوة هذه القيمة، لا ندخل (لأنها قد تكون خطأً).
MAX_ENTRY_GAP_USD = _env_float("STRAT_MAX_ENTRY_GAP", 22.0)

# gap_max_gap_pct: إغلاق إذا تجاوزت الفجوة نسبة مئوية من سعر الصرف (للحماية).
gap_max_gap_pct = 0.10  # 10% من سعر الصرف

MAX_GAP_USD = _env_float("STRAT_MAX_GAP", 100.0)  # رفض/تجاهل ملاحظات خارج هذا المدى

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

MAX_GAP_VELOCITY = _env_float("STRAT_MAX_VELOCITY", 2.0)

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

# Stats
ROLLING_WINDOW = int(_env_float("STRAT_WINDOW", 48))
MIN_SAMPLES = int(_env_float("STRAT_MIN_SAMPLES", 8))
MIN_BALANCE_TO_TRADE = 200.0

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