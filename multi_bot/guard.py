# -*- coding: utf-8 -*-
"""
multi_bot/guard.py — طبقة الأمان القائمة على **حقيقة الوسيط** لا على الحالة المحلية.

السبب (2026-10-29): حارس "صفقة واحدة" السابق كان يقرأ `positions_get()` مرة
واحدة على تيرمنال يُقلع للتو فيرجع فارغاً — فانفتح 129 صفقة في وقت واحد و57
على USDCHF. كل الدوال هنا تقرأ من MT5 مباشرة (positions + history_deals)،
وتفشل بأمان (fail-closed): أي شك = منع.
"""
import datetime

from multi_bot import config

# MT5 deal entry types
_ENTRY_IN = 0
_ENTRY_OUT = (1, 2, 3)   # OUT, INOUT, OUT_BY


def _mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None


def normalize(symbol):
    return (config.MT5_SYMBOL_SUFFIX + symbol).upper()


# ---------------------------------------------------------------- positions

def live_positions():
    """الصفقات المفتوحة الآن — من الوسيط مباشرة."""
    mt5 = _mt5()
    if mt5 is None:
        return []
    try:
        return list(mt5.positions_get() or [])
    except Exception:
        return []


def open_position_ids(hours=None):
    """position_id فُتح ولم يُغلق — من سجل الديلات (يكشف ما لا تعرضه positions_get)."""
    mt5 = _mt5()
    if mt5 is None:
        return {}
    hours = int(hours or config.BROKER_DEDUP_HOURS)
    now = datetime.datetime.utcnow()
    frm = now - datetime.timedelta(hours=hours)
    try:
        deals = mt5.history_deals_get(frm, now + datetime.timedelta(hours=6)) or []
    except Exception:
        return {}
    opened = {}
    closed = set()
    for d in deals:
        pid = getattr(d, "position_id", 0) or 0
        if not pid:
            continue
        entry = getattr(d, "entry", None)
        if entry == _ENTRY_IN:
            opened[pid] = getattr(d, "symbol", "") or ""
        elif entry in _ENTRY_OUT:
            closed.add(pid)
    return {p: s for p, s in opened.items() if p not in closed}


def account_exposure():
    """(محجوب؟, السبب). fail-closed: أي شك = محجوب."""
    mt5 = _mt5()
    if mt5 is None:
        return True, "guard_no_mt5"
    pos = live_positions()
    if pos:
        syms = sorted({getattr(p, "symbol", "?") for p in pos})
        return True, "broker_position:" + ",".join(syms)
    leftover = open_position_ids()
    if leftover:
        syms = sorted({s for s in leftover.values() if s})
        return True, "broker_deal:" + ",".join(syms)
    return False, ""


# ---------------------------------------------------------------- account

def account():
    mt5 = _mt5()
    if mt5 is None:
        return None
    try:
        return mt5.account_info()
    except Exception:
        return None


def equity():
    a = account()
    return float(a.equity) if a else 0.0


def balance():
    a = account()
    return float(a.balance) if a else 0.0


def realized_pnl(since):
    """صافي المنفّذ (profit + swap + commission) منذ تاريخ محدد."""
    mt5 = _mt5()
    if mt5 is None or since is None:
        return 0.0
    now = datetime.datetime.utcnow()
    try:
        deals = mt5.history_deals_get(since, now + datetime.timedelta(hours=6)) or []
    except Exception:
        return 0.0
    total = 0.0
    for d in deals:
        if getattr(d, "entry", None) in _ENTRY_OUT:
            total += float(getattr(d, "profit", 0.0) or 0.0)
            total += float(getattr(d, "swap", 0.0) or 0.0)
            total += float(getattr(d, "commission", 0.0) or 0.0)
    return round(total, 2)


def day_pnl():
    now = datetime.datetime.utcnow()
    return realized_pnl(datetime.datetime(now.year, now.month, now.day))


def trades_opened_today():
    """عدد الصفقات المفتوحة اليوم — من الوسيط، لأن ملف الحالة لا يُحفظ في السحابة."""
    mt5 = _mt5()
    if mt5 is None:
        return 0
    now = datetime.datetime.utcnow()
    start = datetime.datetime(now.year, now.month, now.day)
    try:
        deals = mt5.history_deals_get(start, now + datetime.timedelta(hours=6)) or []
    except Exception:
        return 0
    n = 0
    for d in deals:
        if getattr(d, "entry", None) != _ENTRY_IN:
            continue
        if getattr(d, "type", None) not in (0, 1):   # BUY / SELL فقط (لا إيداعات)
            continue
        if not (getattr(d, "symbol", "") or ""):
            continue
        n += 1
    return n


def month_pnl():
    now = datetime.datetime.utcnow()
    return realized_pnl(datetime.datetime(now.year, now.month, 1))


def consecutive_losses(lookback_hours=72):
    """عدد الخسائر المتتالية في نهاية السلسلة (بترتيب زمن الإغلاق)."""
    mt5 = _mt5()
    if mt5 is None:
        return 0
    now = datetime.datetime.utcnow()
    frm = now - datetime.timedelta(hours=int(lookback_hours))
    try:
        deals = mt5.history_deals_get(frm, now + datetime.timedelta(hours=6)) or []
    except Exception:
        return 0
    pos = {}
    for d in deals:
        pid = getattr(d, "position_id", 0) or 0
        if not pid or getattr(d, "entry", None) not in _ENTRY_OUT:
            continue
        rec = pos.setdefault(pid, {"t": 0, "pnl": 0.0})
        rec["t"] = max(rec["t"], int(getattr(d, "time", 0) or 0))
        rec["pnl"] += (float(getattr(d, "profit", 0.0) or 0.0)
                       + float(getattr(d, "swap", 0.0) or 0.0)
                       + float(getattr(d, "commission", 0.0) or 0.0))
    streak = 0
    for _pid, rec in sorted(pos.items(), key=lambda kv: kv[1]["t"], reverse=True):
        if rec["pnl"] <= 0:
            streak += 1
        else:
            break
    return streak


# ---------------------------------------------------------------- kill switch

def kill_switch():
    """(محجوب؟, السبب, تفاصيل). يُقرأ من الوسيط لا من ملف حالة محلي."""
    bal = balance()
    if bal <= 0:
        return True, "guard_no_account", {}
    day = day_pnl()
    month = month_pnl()
    streak = consecutive_losses()
    detail = {
        "balance": round(bal, 2),
        "day_pnl": day,
        "month_pnl": month,
        "streak": streak,
        "day_limit": round(-config.DAILY_LOSS_FRAC * bal, 2),
        "month_limit": round(-config.MONTHLY_LOSS_FRAC * bal, 2),
    }
    if day <= -config.DAILY_LOSS_FRAC * bal:
        return True, "kill_daily", detail
    if month <= -config.MONTHLY_LOSS_FRAC * bal:
        return True, "kill_monthly", detail
    if streak >= config.MAX_CONSECUTIVE_LOSSES:
        return True, "kill_streak", detail
    return False, "", detail
