# -*- coding: utf-8 -*-
"""
multi_bot/calendar.py — تقويم اقتصادي + فلتر أحداث
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from multi_bot import config


def _fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _normalize_events(raw):
    events = []
    if isinstance(raw, list):
        events = raw
    elif isinstance(raw, dict):
        for key in ("events", "data", "calendar", "result"):
            if key in raw and isinstance(raw[key], list):
                events = raw[key]
                break
    out = []
    for e in events:
        try:
            out.append({
                "title": e.get("title") or e.get("event") or e.get("name") or "",
                "currency": (e.get("currency") or e.get("Currency") or "").upper(),
                "impact": (e.get("impact") or e.get("Impact") or "").lower(),
                "timestamp": e.get("timestamp") or e.get("date") or e.get("time") or "",
                "source": e.get("source") or "",
            })
        except Exception:
            continue
    return out


def _impact_rank(impact):
    v = (impact or "").lower()
    if "high" in v:
        return 3
    if "medium" in v:
        return 2
    if "low" in v:
        return 1
    return 0


def _load_cache():
    try:
        with open(config.CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(obj):
    try:
        config.ensure_data_dir()
        with open(config.CALENDAR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_events(force_refresh=False):
    cache = _load_cache()
    now = datetime.now(timezone.utc)
    if not force_refresh and cache.get("fetched_at"):
        try:
            fetched = datetime.fromisoformat(cache["fetched_at"])
            if now - fetched < timedelta(hours=6):
                return cache.get("events", [])
        except Exception:
            pass

    raw = _fetch_json(config.FOREX_FACTORY_URL)
    events = _normalize_events(raw or [])
    cache["fetched_at"] = now.isoformat()
    cache["events"] = events
    _save_cache(cache)
    return events


def get_events_for_symbol(symbol, hours_ahead=48):
    try:
        ccy = symbol[:3].upper()
        ccy2 = symbol[3:6].upper()
    except Exception:
        return []
    relevant = []
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=hours_ahead)
    for e in fetch_events():
        if not e.get("currency") or e["currency"] not in (ccy, ccy2):
            continue
        ts = e.get("timestamp") or ""
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue
        if dt is None:
            continue
        if dt < now or dt > deadline:
            continue
        e["_dt"] = dt
        relevant.append(e)
    relevant.sort(key=lambda x: (x.get("_dt") or now, -_impact_rank(x.get("impact", ""))))
    return relevant


def has_high_impact_near(symbol, within_minutes=120):
    events = get_events_for_symbol(symbol, hours_ahead=24)
    now = datetime.now(timezone.utc)
    for e in events:
        dt = e.get("_dt")
        if dt is None:
            continue
        if _impact_rank(e.get("impact", "")) >= 3:
            diff = (dt - now).total_seconds() / 60.0
            if 0 <= diff <= within_minutes:
                return True
    return False
