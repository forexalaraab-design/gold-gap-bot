# -*- coding: utf-8 -*-
"""
multi_bot/analyst.py — آراء المحللين + اتجاهات كبار المتداولين
مصادر مجانية قدر الإمكان: COT report HTML + Yahoo sentiment + تلميحات RSS
"""
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from multi_bot import config


def _fetch(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def get_cot_bias():
    try:
        raw = _fetch(config.COT_URL)
        if not raw:
            return 0.0
        text = raw.lower()
        # محاولة استخراج اتجاه عام من النص (بدون parsing كامل)
        bullish = text.count("long") + text.count("buy") + text.count("increase")
        bearish = text.count("short") + text.count("sell") + text.count("decrease")
        total = bullish + bearish
        if total == 0:
            return 0.0
        return max(-1.0, min(1.0, (bullish - bearish) / total))
    except Exception:
        return 0.0


def get_yahoo_summary(symbol):
    try:
        sym = symbol.upper()
        if sym == "XAUUSD":
            sym = "GC=F"
        else:
            sym = sym + "=X"
        url = config.YAHOO_CHART_URL.replace("{symbol}", sym)
        raw = _fetch(url)
        if not raw:
            return {}
        import json
        data = json.loads(raw)
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        return {
            "regularMarketPrice": meta.get("regularMarketPrice"),
            "regularMarketTime": meta.get("regularMarketTime"),
            "fiftyDayAverage": meta.get("fiftyDayAverage"),
            "twoHundredDayAverage": meta.get("twoHundredDayAverage"),
        }
    except Exception:
        return {}


def analyst_consensus(symbol):
    cot = get_cot_bias()
    yahoo = get_yahoo_summary(symbol)
    price = yahoo.get("regularMarketPrice")
    ma50 = yahoo.get("fiftyDayAverage")
    ma200 = yahoo.get("twoHundredDayAverage")
    score = 0.0
    reasons = []
    if price and ma50 and ma200:
        if price > ma50 > ma200:
            score += 0.4
            reasons.append("above_ma50_ma200")
        elif price < ma50 < ma200:
            score -= 0.4
            reasons.append("below_ma50_ma200")
    score += cot * 0.3
    if cot > 0.2:
        reasons.append("cot_bullish")
    elif cot < -0.2:
        reasons.append("cot_bearish")
    return {
        "score": max(-1.0, min(1.0, score)),
        "side": "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral",
        "reasons": reasons,
        "price": price,
        "ma50": ma50,
        "ma200": ma200,
        "cot_bias": cot,
    }
