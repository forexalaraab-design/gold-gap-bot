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
        pip_value = 1.0
        if symbol.upper().endswith("JPY"):
            pip_value = 0.01
        elif symbol.upper() == "XAUUSD":
            pip_value = 1.0
        sl_pips = abs(entry_price - sl_price) / pip_value
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
