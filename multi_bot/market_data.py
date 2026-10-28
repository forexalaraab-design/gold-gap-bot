# -*- coding: utf-8 -*-
"""
multi_bot/market_data.py — مصدر السعر الأساسي: MT5 نفسه.

السبب (2026-10-29): السحابة كانت تقرأ Yahoo، وهو محجوب على مراكز البيانات،
فكانت كل جولة تُرجع `0 opportunities` في 9 ثوان. MT5 مثبَّت ومتصل أصلاً على
الـ runner، فليكن هو المصدر الأول — وYahoo احتياطي محلي فقط.
"""
from multi_bot import config


def _mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None


def normalize(symbol):
    return (config.MT5_SYMBOL_SUFFIX + symbol).upper()


def terminal_ready():
    mt5 = _mt5()
    if mt5 is None:
        return False
    try:
        info = mt5.terminal_info()
        return bool(info and getattr(info, "connected", False))
    except Exception:
        return False


def _empty(source="none"):
    return {
        "price": None, "highs": [], "lows": [], "closes": [],
        "ma50": None, "ma200": None, "source": source,
    }


def fetch_mt5(symbol, bars=None, retries=3, delay=2.0):
    """(بيانات, سبب). بيانات D1 من MT5 + سعر حيّ من الـ tick."""
    import time

    mt5 = _mt5()
    if mt5 is None:
        return None, "mt5_missing"
    sym = normalize(symbol)
    bars = int(bars or config.MT5_BARS)
    for attempt in range(1, int(retries) + 1):
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
        rates = None
        try:
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, bars)
        except Exception:
            rates = None
        if rates is not None and len(rates) >= 30:
            break
        if attempt < retries:
            time.sleep(delay)
    if rates is None or len(rates) < 30:
        try:
            if mt5.symbol_info(sym) is None:
                return None, f"symbol_absent:{sym}"
        except Exception:
            pass
        return None, f"no_bars:{sym}"
    highs = [float(v) for v in rates["high"]]
    lows = [float(v) for v in rates["low"]]
    closes = [float(v) for v in rates["close"]]
    price = closes[-1]
    try:
        tick = mt5.symbol_info_tick(sym)
        if tick and tick.bid > 0 and tick.ask > 0:
            price = (float(tick.bid) + float(tick.ask)) / 2.0
    except Exception:
        pass
    ma50 = sum(closes[-50:]) / 50.0 if len(closes) >= 50 else None
    ma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else None
    return {
        "price": price, "highs": highs, "lows": lows, "closes": closes,
        "ma50": ma50, "ma200": ma200, "source": "mt5",
    }, "ok"


def fetch(symbol, yahoo_fallback=None):
    """
    (بيانات, سبب). MT5 أولاً؛ ياهو فقط إن فشل MT5 (بيئة محلية).
    `yahoo_fallback` دالة اختيارية تُستدعى عند الحاجة فقط.
    """
    if terminal_ready():
        data, why = fetch_mt5(symbol)
        if data:
            return data, "mt5"
        mt5_reason = why
    else:
        mt5_reason = "mt5_not_connected"
    if yahoo_fallback is not None:
        try:
            yd = yahoo_fallback(symbol)
            if yd and yd.get("price") is not None:
                yd = dict(yd)
                yd["source"] = "yahoo"
                return yd, "yahoo"
        except Exception:
            pass
    return _empty(), mt5_reason
