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


def calculate_sl_tp(side, entry_price, highs, lows, closes):
    atr = atr_from_true_range(highs, lows, closes)
    if atr is None or math.isnan(atr) or atr <= 0:
        sl_dist = config.SL_ATR_MULT * 1.0
        tp_dist = config.TP_ATR_MULT * 1.0
    else:
        sl_dist = config.SL_ATR_MULT * atr
        tp_dist = config.TP_ATR_MULT * atr
    # Cap SL/TP to reasonable ranges to avoid broker rejection
    if entry_price > 100:
        max_sl = entry_price * 0.02
        max_tp = entry_price * 0.04
    elif entry_price > 10:
        max_sl = entry_price * 0.01
        max_tp = entry_price * 0.02
    else:
        max_sl = entry_price * 0.005
        max_tp = entry_price * 0.01
    sl_dist = min(sl_dist, max_sl)
    tp_dist = min(tp_dist, max_tp)
    if side == "BUY":
        sl = entry_price - sl_dist
        tp = entry_price + tp_dist
    else:
        sl = entry_price + sl_dist
        tp = entry_price - tp_dist
    rr = tp_dist / sl_dist if sl_dist > 0 else 0.0
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
        return lots
    except Exception:
        return 0.01


def jitter_price(price, frac=config.ENTRY_JITTER_FRAC):
    try:
        return price * (1.0 + (__import__("random").random() - 0.5) * 2.0 * frac)
    except Exception:
        return price


def jitter_sl_tp(sl, tp):
    try:
        j = config.SL_TP_JITTER_USD * (__import__("random").random() - 0.5) * 2.0
        return sl + j, tp - j
    except Exception:
        return sl, tp
