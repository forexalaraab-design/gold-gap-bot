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

# الحجم: 0.03 لوت = 3 أونصات ذهب ≈ $3 PnL لكل حركة 1$ في السعر
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
# (مثلاً: الفجوة واضحة والسرعة غير خطرة).
Z_ENTRY_SOFT = _env_float("STRAT_Z_ENTRY_SOFT", 1.5)

# Z_EXIT: إغلاق إذا عاد |z| إلى هذا المستوى (عندما يتراجع الانحراف).
Z_EXIT = _env_float("STRAT_Z_EXIT", 0.5)

# Z_STOP: حدود上限 لـ |z| قبل اعتباره خطرًا أو غير مستدام.
Z_STOP = _env_float("STRAT_Z_STOP", 3.5)

# SL_AFTER_ENTRY_USD: المسافة الدنيا لوقف الخسارة بعد الفتح (بالفجوة/الوحدات).
SL_AFTER_ENTRY_USD = _env_float("STRAT_SL_USD", 8.0)

# MAX_ENTRY_GAP_USD: إذا تجاوزت الفجوة هذه القيمة، لا ندخل (لأنها قد تكون خطأً).
MAX_ENTRY_GAP_USD = _env_float("STRAT_MAX_ENTRY_GAP", 22.0)

# gap_max_gap_pct: إغلاق إذا تجاوزت الفجوة نسبة مئوية من سعر الصرف (للحماية).
gap_max_gap_pct = 0.10  # 10% من سعر الصرف

MAX_GAP_USD = _env_float("STRAT_MAX_GAP", 100.0)  # رفض/تجاهل ملاحظات خارج هذا المدى

# FLTR ضوضاء السوق: لا تدخل صفقة إلا إذا كانت الفجوة ≥ قيمة واضحة
# 0.50 → 1.00: نزيد عتبة الدخول لتقليل الدخول في تذبذبات صغيرة.
MIN_GAP_USD = _env_float("STRAT_MIN_GAP", 1.50)

# COOLDOWN_MINUTES: انتظار بعد إغلاق صفقة قبل فتح أخرى (تجنب المتتابعات الخاطئة).
# 5.0 → 3.0: عدد أقل لكنه لا يزال واقعيًا.
COOLDOWN_MINUTES = _env_float("STRAT_COOLDOWN_MIN", 3.0)

# MAX_TRADES_PER_DAY: الحد الأقصى لعدد الصفقات في اليوم.
MAX_TRADES_PER_DAY = int(_env_float("STRAT_MAX_TRADES_PER_DAY", 1))

FORCE_TEST_OPEN = _env_bool("STRAT_FORCE_TEST_OPEN", False)

TRADING_FEES_PER_TRADE_LOT = _env_float("STRAT_FEES_PER_LOT", 8.0)
DYNAMIC_PROFIT_FLOOR_USD = _env_float("STRAT_PROFIT_FLOOR", 2.0)
PROFIT_FLOOR_PER_OLOT_USD = _env_float("STRAT_PROFIT_FLOOR_LOT", 0.2)

# تثبيت الأرباح: إغلاق فوري عند بلوغ ربح صافي محدد
# 2.0 → 3.0: نزيد الهدف قليلاً لنحمي الأرباح وتجنب التقلبات.
PROFIT_TARGET_USD = _env_float("STRAT_PROFIT_TARGET", 3.0)

# TRAILING_ARM_USD: تتبع الأرباح يبدأ عندما يصل الـ PnL الصافي إلى هذه القيمة.
# 0.30 → 0.30: netting $0.30 以上でトラリング開始（そのまま）
TRAILING_ARM_USD = _env_float("STRAT_TRAILING_ARM", 0.30)

# TRAILING_BACK_USD: إذا تراجع الربح من ذروته بهذا المقدار، نغلق الصفقة.
# 0.50 → 0.30: نغلق أسرع عند تراجع الأرباح (حماية من العودة الخاسرة).
TRAILING_BACK_USD = _env_float("STRAT_TRAILING_BACK", 0.30)

# MAX_HOLD_HOURS: أقصى وقت للحفاظ على الصفقة مفتوحة قبل الإغلاق الإلزامي.
# 2.0 → 4.0: وقت أطول قليلاً لإعطاء الفرصة للاستعادة، لكن نغلق في النهاية.
MAX_HOLD_HOURS = _env_float("STRAT_MAX_HOLD_HOURS", 2.0)

# الحد الأقصى للخسارة لصفقة واحدة (إغلاق آلي).
MAX_LOSS_USD = _env_float("STRAT_MAX_LOSS_USD", 2.0)

# الحد اليومي للخسارة (دائرة أمان).
MAX_DAILY_LOSS_USD = _env_float("STRAT_MAX_DAILY_LOSS_USD", 30.0)

# أقصى عدد من الخسائر المتتالية قبل التوقف (دائرة أمان).
MAX_CONSECUTIVE_LOSSES = int(_env_float("STRAT_MAX_CONSEC_LOSSES", 3.0))

SESSION_GUARD = os.environ.get("STRAT_SESSION_GUARD", "1") == "1"
LIVE_TRADING_START_HOUR = _env_float("STRAT_SESSION_START", 22.0)
LIVE_TRADING_END_HOUR = _env_float("STRAT_SESSION_END", 5.0)

MAX_GAP_VELOCITY = _env_float("STRAT_MAX_VELOCITY", 5.0)
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
DURATION_MIN = _env_float("CBOT_DURATION_MIN", 4.5)
GLOBAL_POLL_SEC = _env_float("CBOT_GLOBAL_POLL_SEC", 3)
APPEND_EVERY_SEC = 60.0
APPEND_TOLERANCE = 0.02
MAX_HISTORY_ROWS = 2000

# ===== Misc =====
VERSION_REQ = True
CONNECT_TIMEOUT = 30