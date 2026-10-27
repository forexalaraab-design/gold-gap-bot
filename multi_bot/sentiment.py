# -*- coding: utf-8 -*-
"""
multi_bot/sentiment.py — تحليل مشاعر بسيط من أخبار + RSS
ملاحظة: بدون مفاتيح مدفوعة. نستخدم RSS + scraping بسيط.
"""
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from multi_bot import config


RSS_SOURCES = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.dailyfx.com/feeds/market-news",
    "https://www.fxstreet.com/rss/news",
    "https://www.investing.com/rss/news.rss",
    "https://rss.app/feeds/RssNews.xml?feedId=1035",
]

FOREX_GOLD_KEYWORDS = {
    "XAUUSD": ["gold", "xau", "xauusd", "precious metals", "bullion", "fed", "dollar", "usd", "yield", "inflation"],
    "NAS100": ["nasdaq", "^ndx", "nas100", "tech stocks", "s&p 500", "spx", "technology", "nvidia", "apple", "microsoft"],
    "EURUSD": ["eur/usd", "eurusd", "euro", "ecb", "eurozone", "germany", "france", "italy"],
    "GBPUSD": ["gbp/usd", "gbpusd", "pound", "sterling", "boe", "uk", "britain", "bank of england"],
    "USDJPY": ["usd/jpy", "usdjpy", "yen", "boj", "japan", "tokyo"],
    "USDCHF": ["usd/chf", "usdchf", "franc", "snb", "swiss"],
    "AUDUSD": ["aud/usd", "audusd", "aussie", "rba", "australia", "commodity"],
    "NZDUSD": ["nzd/usd", "nzdusd", "kiwi", "rbnz", "new zealand"],
    "USDCAD": ["usd/cad", "usdcad", "loonie", "boc", "canada", "oil"],
}


def _fetch_rss(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", errors="ignore")
            return text
    except Exception:
        return ""


def _extract_text(items, patterns):
    found = []
    for it in items:
        blob = (it.get("title", "") + " " + it.get("summary", "") + " " + it.get("description", "")).lower()
        for p in patterns:
            if p.lower() in blob:
                found.append(it)
                break
    return found


def _simple_sentiment(text):
    bullish = ["up", "rise", "gain", "bullish", "higher", "surge", "rally", "strong", "beat", "positive", "growth"]
    bearish = ["down", "fall", "drop", "bearish", "lower", "plunge", "weak", "miss", "negative", "recession", "cut"]
    score = 0
    for w in bullish:
        score += text.lower().count(w)
    for w in bearish:
        score -= text.lower().count(w)
    return max(-1.0, min(1.0, score / 8.0))


def get_symbol_sentiment(symbol, hours=24):
    try:
        patterns = FOREX_GOLD_KEYWORDS.get(symbol.upper(), [symbol.upper()])
    except Exception:
        return 0.0, []

    texts = []
    items = []
    for url in RSS_SOURCES:
        raw = _fetch_rss(url)
        if not raw:
            continue
        titles = re.findall(r"<title>(.*?)</title>", raw, flags=re.S)
        descs = re.findall(r"<description>(.*?)</description>", raw, flags=re.S)
        for i, t in enumerate(titles[:20]):
            d = descs[i] if i < len(descs) else ""
            items.append({"title": t, "summary": d, "description": d})
            texts.append(t + " " + d)

    matched = _extract_text(items, patterns)
    matched_text = " ".join((x.get("title", "") + " " + x.get("summary", "") for x in matched))
    score = _simple_sentiment(matched_text)
    return score, matched[:10]
