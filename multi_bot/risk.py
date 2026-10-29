# -*- coding: utf-8 -*-
"""
multi_bot/risk.py — إدارة مخاطر + حساب SL/TP ديناميكياً
"""
import math

from multi_bot import config


def atr_from_true_range(highs, lows, closes, period=14):
    try:
        n = len(highs)
        if n < period + 1:
            return None
        trs = []
        for i in range(1, n):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        atr = sum(trs[-period:]) / period
        return atr
    except Exception:
        return None


def calculate_sl_tp(side, entry_price, highs, lows, closes, symbol=""):
    atr = atr_from_true_range(highs, lows, closes)
    sym = (symbol or "").upper()

    # Daily-style: fixed point distance from entry, adjusted by ATR and symbol
    if sym in ("XAUUSD", "NAS100"):
        base_points = 25
        tp_points = 50
    elif sym.endswith("JPY"):
        base_points = 20
        tp_points = 40
    elif sym in ("EURUSD", "GBPUSD", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD"):
        base_points = 15
        tp_points = 30
    else:
        base_points = 15
        tp_points = 30

    if atr and not math.isnan(atr) and atr > 0:
        # Scale by ATR so stop distance adapts to volatility, but cap to daily range
        if sym in ("XAUUSD", "NAS100"):
            sl_dist = max(atr * 0.8, base_points * 0.01)
            tp_dist = max(atr * 1.6, tp_points * 0.01)
        elif sym.endswith("JPY"):
            sl_dist = max(atr * 0.8, base_points * 0.01)
            tp_dist = max(atr * 1.6, tp_points * 0.01)
        else:
            sl_dist = max(atr * 0.8, base_points * 0.0001)
            tp_dist = max(atr * 1.6, tp_points * 0.0001)
    else:
        # Fallback fixed daily-style points
        if sym in ("XAUUSD", "NAS100"):
            sl_dist = base_points * 0.01
            tp_dist = tp_points * 0.01
        elif sym.endswith("JPY"):
            sl_dist = base_points * 0.01
            tp_dist = tp_points * 0.01
        else:
            sl_dist = base_points * 0.0001
            tp_dist = tp_points * 0.0001

    if side == "BUY":
        sl = entry_price - sl_dist
        tp = entry_price + tp_dist
    else:
        sl = entry_price + sl_dist
        tp = entry_price - tp_dist

    rr = abs(tp - entry_price) / abs(entry_price - sl) if (entry_price - sl) != 0 else 0.0
    if rr < config.MIN_RR:
        return None, None
    return sl, tp


def position_size(balance, entry_price, sl_price, symbol):
    try:
        risk_per_trade = balance * config.RISK_PER_TRADE
        sym = symbol.upper()
        if sym.endswith("JPY"):
            pip_size = 0.01
        elif sym == "XAUUSD":
            pip_size = 0.01
        elif sym == "NAS100":
            pip_size = 1.0
        else:
            pip_size = 0.0001
        sl_pips = abs(entry_price - sl_price) / pip_size
        if sl_pips <= 0:
            return 0
        lots = risk_per_trade / (sl_pips * 1000)
        lots = max(0.01, round(lots, 2))
        # 2026-10-29: سقف صلب في الكود — لا يُتجاوز من env
        return min(lots, getattr(config, "MAX_LOT", 0.01))
    except Exception:
        return 0.01


def jitter_price(price, frac=config.ENTRY_JITTER_FRAC):
    try:
        return price * (1.0 + (__import__("random").random() - 0.5) * 2.0 * frac)
    except Exception:
        return price


def jitter_sl_tp(sl, tp, ref=None):
    """
    2026-10-29: التشويش صار **نسبياً** عندما يُمرَّر `ref` (سعر الدخول).
    العطل السابق: `SL_TP_JITTER_USD=0.05` إزاحة سعرية مطلقة — مقبولة للذهب
    ($0.05) ومدمّرة للفوركس (0.05 على 1.1160 = 500 نقطة). النتيجة المقيسة:
    وقف EURUSD خرج 293 نقطة بدل 49، والذهب $51.78 خطراً على حساب $91.56.
    """
    try:
        import random
        if ref is not None:
            dist = abs(float(ref) - float(sl))
            j = dist * config.SL_TP_JITTER_FRAC * (random.random() - 0.5) * 2.0
        else:
            j = config.SL_TP_JITTER_USD * (random.random() - 0.5) * 2.0
        new_sl, new_tp = sl + j, tp - j
        # لا نسمح للتشويش أن يقلب الاتجاه
        if ref is not None:
            if float(ref) > float(sl) and not (new_sl < float(ref) < new_tp):
                return sl, tp
            if float(ref) < float(sl) and not (new_sl > float(ref) > new_tp):
                return sl, tp
        return new_sl, new_tp
    except Exception:
        return sl, tp


def risk_usd(symbol, entry_price, sl_price, lots):
    """
    خسارة الصفقة عند الوقف بالدولار — من مواصفات الوسيط لا من تقدير.
    هذه هي القيمة التي تحكم بوابة المخاطرة.
    """
    try:
        import MetaTrader5 as mt5
        sym = (config.MT5_SYMBOL_SUFFIX + symbol).upper()
        si = mt5.symbol_info(sym)
        if si is None:
            mt5.symbol_select(sym, True)
            si = mt5.symbol_info(sym)
        if si is None or not si.trade_tick_size:
            return None
        per_price = float(si.trade_tick_value) / float(si.trade_tick_size)
        return abs(float(entry_price) - float(sl_price)) * per_price * float(lots)
    except Exception:
        return None
