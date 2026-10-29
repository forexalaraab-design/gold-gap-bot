# -*- coding: utf-8 -*-
"""
multi_bot/scanner.py — فحص كل الأزواج وتقييم الفرص

2026-10-29: المصدر الأساسي أصبح MT5 (market_data)، وكل رفض يُسجَّل بسببه
بدل `except: pass`. الدوال العامة محفوظة التوقيع (`_fetch_yahoo`,
`_technical_score`, `score_opportunity`, `scan_all_symbols`).
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

from multi_bot import config, guard, market_data
from multi_bot.calendar import get_events_for_symbol, has_high_impact_near
from multi_bot.sentiment import get_symbol_sentiment
from multi_bot.analyst import analyst_consensus
from multi_bot.risk import (calculate_sl_tp, position_size, jitter_price, jitter_sl_tp,
                            risk_usd)


def _fetch_yahoo(symbol):
    """احتياطي محلي فقط — Yahoo محجوب على مراكز البيانات."""
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
            "source": "yahoo",
        }
    except Exception:
        return {"price": None, "highs": [], "lows": [], "closes": [],
                "ma50": None, "ma200": None, "source": "yahoo_failed"}


def _fetch_prices(symbol):
    """(بيانات, سبب). MT5 أولاً، وياهو احتياطي."""
    return market_data.fetch(symbol, yahoo_fallback=_fetch_yahoo)


def _technical_score(symbol, yahoo):
    try:
        price = yahoo.get("price")
        closes = yahoo.get("closes", [])
        highs = yahoo.get("highs", [])
        lows = yahoo.get("lows", [])
        if price is None or len(closes) < 20:
            return 0.0, "neutral", ["no_price"]
        reasons = []
        score = 0.0

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

            if "breakout" not in reasons and "breakdown" not in reasons:
                if len(closes) >= 3:
                    slope = closes[-1] - closes[-3]
                    if slope > 0:
                        score += 0.15
                        reasons.append("up_slope")
                    elif slope < 0:
                        score -= 0.15
                        reasons.append("down_slope")

        recent_change = closes[-1] - closes[-5] if len(closes) >= 5 else 0
        if score > 0.1 and recent_change >= 0:
            side = "BUY"
        elif score < -0.1 and recent_change <= 0:
            side = "SELL"
        elif score > 0.1:
            side = "BUY"
        elif score < -0.1:
            side = "SELL"
        else:
            side = "neutral"
        return max(-1.0, min(1.0, score)), side, reasons
    except Exception as exc:
        return 0.0, "neutral", [f"tech_error:{type(exc).__name__}"]


def score_opportunity(symbol, diag=None):
    """
    فرصة أو None. `diag` (اختياري) يُملأ بالسبب — لا رفض صامت بعد اليوم.
    """
    def _drop(reason, **extra):
        if diag is not None:
            diag.update({"symbol": symbol, "reason": reason, **extra})
        return None

    try:
        if has_high_impact_near(symbol, within_minutes=config.HIGH_IMPACT_BLOCK_MINUTES):
            return _drop("high_impact_window")

        data, source = _fetch_prices(symbol)
        if diag is not None:
            diag["source"] = source
        if data.get("price") is None:
            return _drop(f"no_price:{source}")

        tech_score, tech_side, tech_reasons = _technical_score(symbol, data)
        sent_score, _sent_items = get_symbol_sentiment(symbol)
        analyst = analyst_consensus(symbol)
        analyst_score = analyst.get("score", 0.0)
        events = get_events_for_symbol(symbol, hours_ahead=24)

        total = tech_score * 0.60 + sent_score * 0.20 + analyst_score * 0.20
        total = max(-1.0, min(1.0, total))
        if diag is not None:
            diag.update({
                "tech": round(float(tech_score), 3),
                "sent": round(float(sent_score), 3),
                "analyst": round(float(analyst_score), 3),
                "total": round(float(total), 3),
                "tech_reasons": tech_reasons,
            })
        if abs(total) < config.MIN_CONFIDENCE:
            return _drop("below_threshold")

        side = tech_side
        if side == "neutral":
            side = "BUY" if total > 0 else "SELL"

        entry = float(data["price"])
        sl, tp = calculate_sl_tp(side, entry, data.get("highs", []),
                                 data.get("lows", []), data.get("closes", []),
                                 symbol=symbol)
        if sl is None or tp is None:
            return _drop("no_sl_tp")
        if side == "BUY" and not (sl < entry < tp):
            return _drop("bad_stops_buy")
        if side == "SELL" and not (sl > entry > tp):
            return _drop("bad_stops_sell")

        balance = guard.equity()
        if balance <= 0:
            try:
                with open(config.STATE_FILE, "r", encoding="utf-8") as f:
                    balance = float(json.load(f).get("balance", 0.0))
            except Exception:
                balance = 0.0
        if balance <= 0:
            return _drop("no_account_equity")

        entry = jitter_price(entry, config.ENTRY_JITTER_FRAC)
        sl, tp = jitter_sl_tp(sl, tp, ref=entry)
        lots = min(config.MAX_LOT, position_size(balance, entry, sl, symbol))
        if lots < 0.01:
            return _drop("lots_below_min", balance=round(balance, 2))

        # 2026-10-29: بوّابة المخاطرة النسبية — بديل بوابة 300$ المسطّحة.
        # خطر الصفقة الواحدة عند الوقف ≤ MAX_RISK_PCT_PER_TRADE من الحقوق.
        loss = risk_usd(symbol, entry, sl, lots)
        budget = config.MAX_RISK_PCT_PER_TRADE * balance
        if loss is None:
            return _drop("risk_unknown", balance=round(balance, 2))
        if loss > budget:
            return _drop("risk_over_budget",
                         risk_usd=round(loss, 2), budget=round(budget, 2),
                         pct=round(100.0 * loss / balance, 1))

        return {
            "symbol": symbol,
            "score": round(float(total), 4),
            "side": side,
            "entry": round(float(entry), 5),
            "sl": round(float(sl), 5),
            "tp": round(float(tp), 5),
            "lots": round(float(lots), 2),
            "risk_usd": round(float(loss), 2),
            "source": source,
            "reasons": tech_reasons + [f"sent={sent_score:.2f}", f"analyst={analyst_score:.2f}"],
            "events": [{"title": e.get("title"), "impact": e.get("impact"),
                        "time": str(e.get("_dt"))} for e in events[:3]],
        }
    except Exception as exc:
        return _drop(f"exception:{type(exc).__name__}")


def scan_all_symbols_detailed():
    """(فرص, أسباب). كل رمز يُسجَّل: فرصة أو سبب رفضه."""
    opportunities = []
    reasons = {}
    for symbol in config.SYMBOLS:
        diag = {}
        opp = score_opportunity(symbol, diag=diag)
        reasons[symbol] = diag
        if opp:
            opportunities.append(opp)
    opportunities.sort(key=lambda x: abs(x["score"]), reverse=True)
    return opportunities[: config.MAX_TRADES_PER_DAY], reasons


def scan_all_symbols():
    """التوقيع القديم محفوظ — القائمة فقط."""
    return scan_all_symbols_detailed()[0]


def _write_json(path, payload):
    try:
        config.ensure_data_dir()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_opportunities(opportunities):
    _write_json(config.OPPORTUNITIES_FILE, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "count": len(opportunities),
        "opportunities": opportunities,
    })


def save_scan_reasons(reasons):
    """سجل الأسباب — يجعل الصمت مرئياً (كان `0 opportunities` بلا تفسير)."""
    _write_json(config.SCAN_REASONS_FILE, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbols": len(reasons),
        "reasons": reasons,
    })
