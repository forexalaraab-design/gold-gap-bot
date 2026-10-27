# -*- coding: utf-8 -*-
"""
multi_bot/scanner.py — فحص كل الأزواج وتقييم الفرص
"""
import json
import os
import random
import urllib.request
from datetime import datetime, timezone

from multi_bot import config
from multi_bot.calendar import get_events_for_symbol, has_high_impact_near
from multi_bot.sentiment import get_symbol_sentiment
from multi_bot.analyst import analyst_consensus
from multi_bot.risk import calculate_sl_tp, position_size, jitter_price, jitter_sl_tp


def _fetch_yahoo(symbol):
    try:
        sym = symbol.upper()
        mapped = getattr(config, "YAHOO_SYMBOL_MAP", {}).get(sym)
        if sym == "XAUUSD":
            sym = "GC=F"
        elif mapped:
            sym = mapped
        else:
            sym = sym + "=X"
        url = config.YAHOO_CHART_URL.replace("{symbol}", sym)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        timestamps = result.get("timestamp", [])
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        closes = quotes.get("close", [])
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        return {
            "price": price,
            "highs": [x for x in highs if x is not None],
            "lows": [x for x in lows if x is not None],
            "closes": [x for x in closes if x is not None],
            "ma50": meta.get("fiftyDayAverage"),
            "ma200": meta.get("twoHundredDayAverage"),
        }
    except Exception:
        return {"price": None, "highs": [], "lows": [], "closes": [], "ma50": None, "ma200": None}


def _technical_score(symbol, yahoo):
    try:
        price = yahoo.get("price")
        closes = yahoo.get("closes", [])
        highs = yahoo.get("highs", [])
        lows = yahoo.get("lows", [])
        if price is None or len(closes) < 20:
            return 0.0, "neutral", []
        reasons = []
        score = 0.0

        # Fallback: compute MAs from closes if Yahoo metadata is missing
        ma50 = yahoo.get("ma50")
        ma200 = yahoo.get("ma200")
        if ma50 is None and len(closes) >= 50:
            ma50 = sum(closes[-50:]) / 50.0
        if ma200 is None and len(closes) >= 200:
            ma200 = sum(closes[-200:]) / 200.0

        if ma50 is not None and ma200 is not None:
            if price > ma50 and price > ma200:
                score += 0.4
                reasons.append("above_ma")
            elif price < ma50 and price < ma200:
                score -= 0.4
                reasons.append("below_ma")
        elif ma50 is not None:
            if price > ma50:
                score += 0.2
                reasons.append("above_ma50")
            else:
                score -= 0.2
                reasons.append("below_ma50")

        recent = closes[-10:]
        if len(recent) >= 2:
            if recent[-1] > max(recent[:-1]):
                score += 0.2
                reasons.append("breakout")
            if recent[-1] < min(recent[:-1]):
                score -= 0.2
                reasons.append("breakdown")

            # Momentum fallback: use last 3-bar slope when no breakout
            if "breakout" not in reasons and "breakdown" not in reasons:
                if len(closes) >= 3:
                    slope = closes[-1] - closes[-3]
                    if slope > 0:
                        score += 0.15
                        reasons.append("up_slope")
                    elif slope < 0:
                        score -= 0.15
                        reasons.append("down_slope")

        side = "BUY" if score > 0.1 else "SELL" if score < -0.1 else "neutral"
        return max(-1.0, min(1.0, score)), side, reasons
    except Exception:
        return 0.0, "neutral", []


def score_opportunity(symbol):
    try:
        if has_high_impact_near(symbol, within_minutes=config.HIGH_IMPACT_BLOCK_MINUTES):
            return None
        yahoo = _fetch_yahoo(symbol)
        if yahoo.get("price") is None:
            return None
        tech_score, tech_side, tech_reasons = _technical_score(symbol, yahoo)
        sent_score, sent_items = get_symbol_sentiment(symbol)
        analyst = analyst_consensus(symbol)
        analyst_score = analyst.get("score", 0.0)
        events = get_events_for_symbol(symbol, hours_ahead=24)
        events_score = 0.0
        if events:
            top = events[0]
            impact = 0.0
            if "high" in (top.get("impact") or "").lower():
                impact = 0.3
            elif "medium" in (top.get("impact") or "").lower():
                impact = 0.15
            events_score = impact
        total = (
            tech_score * 0.60
            + sent_score * 0.20
            + analyst_score * 0.20
        )
        total = max(-1.0, min(1.0, total))
        if abs(total) < config.MIN_CONFIDENCE:
            return None
        side = tech_side
        if side == "neutral":
            side = "BUY" if total > 0 else "SELL"
        entry = float(yahoo["price"])
        sl, tp = calculate_sl_tp(side, entry, yahoo.get("highs", []), yahoo.get("lows", []), yahoo.get("closes", []))
        if sl is None or tp is None:
            return None
        entry = jitter_price(entry, config.ENTRY_JITTER_FRAC)
        sl, tp = jitter_sl_tp(sl, tp)
        balance = 10000.0
        try:
            state_path = config.STATE_FILE
            if os.path.exists(state_path):
                with open(state_path, "r", encoding="utf-8") as f:
                    st = json.load(f)
                balance = float(st.get("balance", 10000.0))
        except Exception:
            balance = 10000.0
        lots = position_size(balance, entry, sl, symbol)
        if lots < 0.01:
            return None
        return {
            "symbol": symbol,
            "score": round(float(total), 4),
            "side": side,
            "entry": round(float(entry), 5),
            "sl": round(float(sl), 5),
            "tp": round(float(tp), 5),
            "lots": round(float(lots), 2),
            "reasons": tech_reasons + [f"sent={sent_score:.2f}", f"analyst={analyst_score:.2f}"],
            "events": [{"title": e.get("title"), "impact": e.get("impact"), "time": str(e.get("_dt"))} for e in events[:3]],
        }
    except Exception:
        return None


def scan_all_symbols():
    opportunities = []
    for symbol in config.SYMBOLS:
        opp = score_opportunity(symbol)
        if opp:
            opportunities.append(opp)
    opportunities.sort(key=lambda x: abs(x["score"]), reverse=True)
    return opportunities[: config.MAX_TRADES_PER_DAY]


def save_opportunities(opportunities):
    try:
        config.ensure_data_dir()
        out = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "count": len(opportunities),
            "opportunities": opportunities,
        }
        with open(config.OPPORTUNITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
