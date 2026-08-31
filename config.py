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

# Self-built thresholds (statistical), replaced by measured scale after warmup.
# Tunables can be overridden via repo secrets (STRAT_*) so the effective
# configuration is never visible in the public repository.
Z_ENTRY = _env_float("STRAT_Z_ENTRY", 2.0)          # enter when |z| >= Z_ENTRY
Z_EXIT = _env_float("STRAT_Z_EXIT", 0.5)            # exit when |z| <= Z_EXIT (reverted)
Z_STOP = _env_float("STRAT_Z_STOP", 3.5)            # hard stop for the gap itself (sanity)
SL_AFTER_ENTRY_USD = _env_float("STRAT_SL_USD", 8.0)  # min SL distance past entry (gap units)
MAX_ENTRY_GAP_USD = _env_float("STRAT_MAX_ENTRY_GAP", 50.0)  # reject phantom/news spikes
MAX_GAP_USD = _env_float("STRAT_MAX_GAP", 100.0)    # reject/strip observations beyond this
COOLDOWN_MINUTES = _env_float("STRAT_COOLDOWN_MIN", 15.0)  # pause re-entry after a close
FORCE_TEST_OPEN = _env_bool("STRAT_FORCE_TEST_OPEN", False)  # open+close one diagnostic trade on start
TRADING_FEES_PER_TRADE_LOT = _env_float("STRAT_FEES_PER_LOT", 8.0)  # est. commission+swap per 1.0 lot in USD
DYNAMIC_PROFIT_FLOOR_USD = _env_float("STRAT_PROFIT_FLOOR", 2.0)    # min net profit (after fees+spread) to bank via dynamic exit
PROFIT_FLOOR_PER_OLOT_USD = _env_float("STRAT_PROFIT_FLOOR_LOT", 0.2)  # extra per 0.01 lot above the gross floor
SESSION_GUARD = os.environ.get("STRAT_SESSION_GUARD", "1") == "1"  # trade only in XAU sessions
USE_MAD = os.environ.get("STRAT_USE_MAD", "1") == "1"  # robust median/MAD scale for z

# Stats
ROLLING_WINDOW = int(_env_float("STRAT_WINDOW", 48))   # last N valid observations
MIN_SAMPLES = int(_env_float("STRAT_MIN_SAMPLES", 8))  # minimum before z can trigger trades
MIN_BALANCE_TO_TRADE = 200.0  # below this, always behave like "log"

# Files / state
HISTORY_FILE = os.path.join(BASE_DIR, "data", "gap_history.csv")
STATE_FILE = os.path.join(BASE_DIR, "data", "bot_state.json")
TRADES_FILE = os.path.join(BASE_DIR, "data", "trades.csv")
PERF_FILE = os.path.join(BASE_DIR, "data", "performance.json")
MAX_CLOSED_TRADES = 200        # records kept in state

# ===== Live loop (live.py) — near real-time coverage =====
# Each GitHub scheduled job (every 5 min) runs a continuous loop for DURATION_MIN
# minutes, polling the global price and reacting to streamed ticks ~immediately.
DURATION_MIN = _env_float("CBOT_DURATION_MIN", 4.5)
GLOBAL_POLL_SEC = _env_float("CBOT_GLOBAL_POLL_SEC", 3)
APPEND_EVERY_SEC = 60.0          # cap history rows: 1 per minute unless fast move
APPEND_TOLERANCE = 0.02          # force an extra row if |gap changed| beyond this
MAX_HISTORY_ROWS = 2000

# ===== Misc =====
VERSION_REQ = True
CONNECT_TIMEOUT = 30          # seconds for the TCP/SSL connection attempt