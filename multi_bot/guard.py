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

# حالة مزامنة السجل — تُقرأ في البوابة (fail-closed)
_HISTORY = {"synced": False, "detail": "not_warmed"}


def _mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None


def normalize(symbol):
    return (config.MT5_SYMBOL_SUFFIX + symbol).upper()


# ---------------------------------------------------------------- warmup
def history_synced():
    return bool(_HISTORY.get("synced"))


def history_detail():
    return _HISTORY.get("detail", "")


def warmup_history(days=30, timeout=45.0, delay=3.0):
    """
    ينتظر مزامنة سجل الديلات بعد إقلاع التيرمنال.

    2026-10-29 (سحابة): عند 23:07:23 قرأ العدّ صفراً، وعند 23:07:35 صار
    day_pnl=-111.8 — أي أن السجل كان **فارغاً كذباً** في الثانية الأولى.
    هذا بالضبط صنف العطل الذي فتح 129 صفقة (قراءة فارغة = سماح).
    فبعد مهلة معقولة: إما ظهرت ديلات (مُزامَن) أو حكمنا بأن الحساب فارغ حقاً.
    """
    import time

    mt5 = _mt5()
    if mt5 is None:
        _HISTORY.update({"synced": False, "detail": "no_mt5"})
        return False, "no_mt5"
    now = datetime.datetime.utcnow()
    frm = now - datetime.timedelta(days=int(days))
    deadline = time.time() + float(timeout)
    n = 0
    started = time.time()
    while True:
        try:
            deals = mt5.history_deals_get(frm, now + datetime.timedelta(hours=6)) or []
            n = len(deals)
        except Exception:
            n = 0
        if n > 0:
            detail = f"deals_{days}d={n} after {time.time() - started:.0f}s"
            _HISTORY.update({"synced": True, "detail": detail})
            return True, detail
        if time.time() >= deadline:
            detail = f"deals_{days}d=0 after {time.time() - started:.0f}s (empty account?)"
            _HISTORY.update({"synced": True, "detail": detail})
            return True, detail
        time.sleep(delay)


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


def _per_price(symbol):
    """دولار لكل وحدة سعر للوت واحد — من مواصفات الوسيط."""
    mt5 = _mt5()
    if mt5 is None:
        return None
    try:
        si = mt5.symbol_info(symbol)
        if si is None:
            mt5.symbol_select(symbol, True)
            si = mt5.symbol_info(symbol)
        if si is None or not si.trade_tick_size:
            return None
        return float(si.trade_tick_value) / float(si.trade_tick_size)
    except Exception:
        return None


def open_risk_usd(positions=None):
    """
    مجموع المخاطرة المفتوحة الآن بالدولار (مسافة الوقف × قيمة النقطة × الحجم).
    None = غير معروف (صفقة بلا وقف) ⇒ fail-closed.
    """
    mt5 = _mt5()
    if mt5 is None:
        return None
    pos = positions if positions is not None else live_positions()
    total = 0.0
    for p in pos:
        sl = float(getattr(p, "sl", 0.0) or 0.0)
        if sl <= 0:
            return None
        per = _per_price(getattr(p, "symbol", ""))
        if per is None:
            return None
        total += abs(float(p.price_open) - sl) * per * float(p.volume)
    return round(total, 2)


def exposure_gate(symbol=None, add_risk_usd=0.0):
    """
    (محجوب؟, السبب). الحدّ لم يُلغَ — انتقل من **عدد الصفقات** إلى **إجمالي
    المخاطرة** (2026-10-30، طلب المستخدم: لا حدّ لعدد الصفقات).

    1) كل رمز صفقة واحدة (لا 57 USDCHF).
    2) مجموع خطر المفتوح + الجديدة ≤ MAX_TOTAL_RISK_PCT من الحقوق.
    3) تعارض بين `positions_get` وسجل الديلات ⇒ محجوب (حالة غير موثوقة).
    """
    mt5 = _mt5()
    if mt5 is None:
        return True, "guard_no_mt5"
    if not history_synced():
        return True, "guard_history_unsynced"

    pos = live_positions()
    if symbol:
        want = normalize(symbol)
        for p in pos:
            if (getattr(p, "symbol", "") or "").upper() == want:
                return True, f"same_symbol:{want}"

    risk = open_risk_usd(pos)
    if risk is None:
        return True, "open_risk_unknown"
    budget = config.MAX_TOTAL_RISK_PCT * equity()
    if budget <= 0:
        return True, "risk_budget_zero"
    if risk + float(add_risk_usd) > budget:
        return True, (f"risk_budget:{risk + float(add_risk_usd):.2f}"
                      f">{budget:.2f} open={risk:.2f} add={float(add_risk_usd):.2f}")

    # صفقة مسجلة في الديلات لكنها غير ظاهرة في positions ⇒ حالة غير موثوقة
    leftover = open_position_ids()
    live_ids = {int(getattr(p, "ticket", 0) or 0) for p in pos}
    orphan = [pid for pid in leftover if pid not in live_ids]
    if orphan:
        return True, f"broker_deal_orphan:{len(orphan)}"
    return False, ""


def account_exposure():
    """التوقيع القديم محفوظ — بلا رمز وبلا مخاطرة مضافة."""
    return exposure_gate()


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


def day_deal_stats():
    """
    تشخيص سجل ديلات اليوم — يفرّق بين "لا صفقات" و"تاريخ مبتور".
    تيرمنال السحابة يُقلع للتو، وسجل الديلات قد يكون ناقصاً قبل المزامنة.
    """
    mt5 = _mt5()
    if mt5 is None:
        return {}
    now = datetime.datetime.utcnow()
    start = datetime.datetime(now.year, now.month, now.day)
    try:
        deals = mt5.history_deals_get(start, now + datetime.timedelta(hours=6)) or []
    except Exception as exc:
        return {"error": type(exc).__name__}
    entries = sum(1 for d in deals if getattr(d, "entry", None) == _ENTRY_IN)
    exits = sum(1 for d in deals if getattr(d, "entry", None) in _ENTRY_OUT)
    times = [int(getattr(d, "time", 0) or 0) for d in deals]
    return {
        "deals": len(deals),
        "entries": entries,
        "exits": exits,
        "first_ts": min(times) if times else 0,
        "last_ts": max(times) if times else 0,
    }


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
