# -*- coding: utf-8 -*-
"""
multi_bot/config.py — إعدادات بوت التحليل اليومي متعدد الأزواج
"""
import os
from datetime import datetime, timezone

# ===== الأزواج =====
SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD", "XAUUSD", "NAS100"
]

# ===== الجدولة =====
SCAN_HOUR_UTC = int(os.environ.get("MULTI_SCAN_HOUR", "8"))
SCAN_MINUTE = int(os.environ.get("MULTI_SCAN_MINUTE", "0"))
HOLD_HOURS = int(os.environ.get("MULTI_HOLD_HOURS", "24"))

# ===== thresholds =====
MIN_CONFIDENCE = float(os.environ.get("MULTI_MIN_CONFIDENCE", "0.30"))
MAX_TRADES_PER_DAY = int(os.environ.get("MULTI_MAX_TRADES", "3"))

# ===== مخاطرة =====
RISK_PER_TRADE = float(os.environ.get("MULTI_RISK_PCT", "0.01"))
MAX_DAILY_LOSS = float(os.environ.get("MULTI_MAX_DAILY_LOSS", "0.03"))
SL_ATR_MULT = float(os.environ.get("MULTI_SL_ATR", "0.5"))
TP_ATR_MULT = float(os.environ.get("MULTI_TP_ATR", "1.0"))
MIN_RR = float(os.environ.get("MULTI_MIN_RR", "1.0"))
HOLD_HOURS = int(os.environ.get("MULTI_HOLD_HOURS", "8"))

# ===== مصادر البيانات =====
FOREX_FACTORY_URL = os.environ.get(
    "FOREX_FACTORY_URL",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
)
TRADING_ECONOMICS_URL = os.environ.get(
    "TRADING_ECONOMICS_URL",
    "https://api.tradingeconomics.com/calendar"
)
COT_URL = os.environ.get(
    "COT_URL",
    "https://www.cftc.gov/dea/financial/financial_major_8.htm"
)
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_INTERVAL = os.environ.get("YAHOO_INTERVAL", "1d")
YAHOO_RANGE = os.environ.get("YAHOO_RANGE", "60d")
YAHOO_SYMBOL_MAP = {
    "NAS100": "^NDX",
}

# ===== MT5 / تنفيذ =====
BROKER = os.environ.get("MULTI_BROKER", "mt5")
MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")
MT5_PATH = os.environ.get("MT5_PATH", "")
MT5_SYMBOL_SUFFIX = os.environ.get("MT5_SYMBOL_SUFFIX", "")

# ===== AI =====
AI_ON = os.environ.get("MULTI_AI_ON", "0") == "1"
AI_API_KEY = os.environ.get("MULTI_AI_API_KEY", "")
AI_PROVIDER = os.environ.get("MULTI_AI_PROVIDER", "openai")
AI_MODEL = os.environ.get("MULTI_AI_MODEL", "gpt-4o-mini")

# ===== ملفات =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
STATE_FILE = os.path.join(DATA_DIR, "multi_bot_state.json")
OPPORTUNITIES_FILE = os.path.join(DATA_DIR, "opportunities.json")
CALENDAR_CACHE_FILE = os.path.join(DATA_DIR, "calendar_cache.json")
TRADES_FILE = os.path.join(DATA_DIR, "multi_trades.csv")

# ===== ساعات التداول =====
#eur: London/NY overlap generally better
HIGH_IMPACT_BLOCK_MINUTES = int(os.environ.get("MULTI_HIGH_IMPACT_BLOCK", "30"))

# ===== حدود حماية =====
MAX_SPREAD_USD = float(os.environ.get("MULTI_MAX_SPREAD_USD", "3.0"))
MIN_VOLUME = int(os.environ.get("MULTI_MIN_VOLUME", "1"))

# ===== تique jitter / humanize =====
ENTRY_JITTER_FRAC = float(os.environ.get("MULTI_ENTRY_JITTER", "0.0002"))
SL_TP_JITTER_USD = float(os.environ.get("MULTI_SL_TP_JITTER", "0.5"))


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
