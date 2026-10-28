# -*- coding: utf-8 -*-
"""
multi_bot/scheduler.py — جدولة يومية + حدود يومية
"""
import json
import os
from datetime import datetime, timezone, timedelta

from multi_bot import config, guard


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
    if max(len(state.get("trades", [])), guard.trades_opened_today()) >= config.MAX_TRADES_PER_DAY:
        return False
    if state.get("daily_pnl", 0.0) <= -config.MAX_DAILY_LOSS:
        return False
    return True


def execution_gate():
    """
    (مسموح؟, السبب). بوابة واحدة تُقرأ في كل جولة، مرتّبة من الأخطر للأقل:
    1) مفتاح التشغيل (env) — افتراضي: مطفأ.
    2) بوابة رأس المال — لا تنفيذ تحت 300$.
    3) مفتاح الإيقاف — خسارة يومية/شهرية/سلسلة خسائر، من الوسيط لا من ملف.
    4) الحد اليومي المحلي.
    5) التعرّض — صفقة واحدة على مستوى الحساب.
    """
    import time
    from multi_bot import guard

    if not config.EXECUTE_ENABLED:
        return False, "execution_disabled"
    equity = guard.equity()
    if equity < config.MIN_EQUITY_USD:
        return False, f"capital_gate:{equity:.2f}<{config.MIN_EQUITY_USD:.0f}"
    blocked, why, _detail = guard.kill_switch()
    if blocked:
        return False, why
    if not can_trade_today():
        return False, "daily_limit"
    if not guard.history_synced():
        return False, "guard_history_unsynced"
    # مهلة استقرار: تيرمنال يُقلع للتو قد يعطي قراءة فارغة كاذبة
    time.sleep(max(0.0, float(config.STABILIZE_SEC)))
    blocked, why = guard.account_exposure()
    if blocked:
        return False, why
    return True, "ok"


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
