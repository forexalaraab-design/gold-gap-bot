# -*- coding: utf-8 -*-
"""
multi_bot/scheduler.py — جدولة يومية + حدود يومية
"""
import json
import os
from datetime import datetime, timezone, timedelta

from multi_bot import config


def _load_state():
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"date": None, "trades": [], "daily_pnl": 0.0, "last_run": None}


def _save_state(state):
    try:
        config.ensure_data_dir()
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def can_trade_today():
    state = _load_state()
    today = _today_str()
    if state.get("date") != today:
        state["date"] = today
        state["trades"] = []
        state["daily_pnl"] = 0.0
        _save_state(state)
        return True
    if len(state.get("trades", [])) >= config.MAX_TRADES_PER_DAY:
        return False
    if state.get("daily_pnl", 0.0) <= -config.MAX_DAILY_LOSS:
        return False
    return True


def record_trade(trade, pnl=0.0):
    state = _load_state()
    state.setdefault("trades", [])
    state["trades"].append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": trade.get("symbol"),
        "side": trade.get("side"),
        "lots": trade.get("lots"),
        "pnl": pnl,
    })
    state["daily_pnl"] = float(state.get("daily_pnl", 0.0)) + float(pnl)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)
