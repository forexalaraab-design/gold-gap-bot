import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
# Store the running token here so later runs can refresh via refreshToken
TOKEN_STORE = os.environ.get("CBOT_TOKEN_STORE", TOKEN_FILE)

# ===== Global gold sources =====
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
YAHOO_OFFSET_USD = 0.0  # GC=F is futures; add offset to approximate spot if needed

# ===== Signal & risk (units: USD per ounce unless stated) =====
SYMBOL = "XAUUSD"
LOT = 0.01  # 1/100 lot (1 oz gold = $1 PnL per $1 move)
# cTrader delivers spot prices for XAUUSD scaled by 10**5 internally
# (symbol.digits=2 is only the display precision). Verified against live quotes.
SPOT_SCALE = 100000.0

# Modes: "log" = record gaps only; "trade" = open/close demo positions
MODE = os.environ.get("CBOT_MODE", "log")

# Self-built thresholds (statistical), replaced by measured sigma after warmup:
Z_ENTRY = 2.0          # enter when |z| >= Z_ENTRY
Z_EXIT = 0.5           # exit when |z| <= Z_EXIT (gap reverted)
Z_STOP = 3.5           # hard stop for the gap itself (sanity)
SL_AFTER_ENTRY_USD = 8.0   # min SL distance past entry (gap units); on 0.01 lot = $8 ~ 8% on $100
MAX_ENTRY_GAP_USD = 50.0   # reject entry if |gap| beyond this (phantom/news spike)
MAX_GAP_USD = 100.0        # reject/strip observations beyond this (data error)

# Stats
ROLLING_WINDOW = 48         # last N valid observations used for mean/std
MIN_SAMPLES = 5             # minimum before z can trigger trades
MIN_BALANCE_TO_TRADE = 200.0  # below this, always behave like "log"

# Files / state
HISTORY_FILE = os.path.join(BASE_DIR, "data", "gap_history.csv")
STATE_FILE = os.path.join(BASE_DIR, "data", "bot_state.json")

# ===== Misc =====
VERSION_REQ = True
CONNECT_TIMEOUT = 30          # seconds for the TCP/SSL connection attempt