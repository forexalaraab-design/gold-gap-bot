# -*- coding: utf-8 -*-
"""
live_mt5.py — MT5 (FP Markets) سائق التداول.

ينسخ قرار الفتح/الإغلاق من main.py حرفياً (نفس البنود) لكن التنفيذ
عبر MT5 حيث SL/TP سيرفر مقبول من لحظة الطلب (عكس cTrader). يُشغَّل
في دورة قصيرة على GitHub Actions (مثل live.py) مع حفظ الحالة في data/.

المصادر المرجعية (لا تتغير): main.run_trade_cycle / ClosingManager —
هذا الملف يعاود استخدام دوال main النقية (مومنتوم/فلاتر/بشرنة/تسجيل)
بنفس المنطق حرفياً دون نسخه، لأن ربط run_trade_cycle الكامل يتطلب
واجهة Twisted/cTrader مساوية (resolve_position_id وغيره).
"""

import json
import os
import types
import time
from datetime import datetime, timezone

import config
import gold_price
import main as _main
import mt5_broker

__all__ = ["mt5_run_duration"]


def utcnow_iso():
    return _main.utcnow_iso()


def _now_unix():
    return time.time()


def _load_state():
    return _main.load_state()


def _save_state(state):
    _main.save_state(state)


def _detected_spread_usd(result=None):
    return _main._detected_spread_usd(result)


# ============================================================================
# أدوات تحويل — من object صفقة cbot إلى SimpleNamespace يطبّقه ClosingManager
# ============================================================================

def _pos_ns(broker_pos):
    """يحوّل dict صفقة mt5_broker إلى object بالبنية التي تتوقعها
    ClosingManager / dynamic_pnl_usd (tradeData.volume, tradeData.tradeSide,
    commission, swap, positionId…). tradeSide: BUY=1, SELL=2 (cTrader).
    volume: الوحدات الداخلية لـ dynamic_pnl_usd — XAUUSD 0.01 لوت = 100
    وحدة سعر داخلية (تطابق main.py سطر 552). حجم MT5 الفعلي لا يُستخدم
    في الحساب لأن CLOT (0.01) ثابت وحساباتنا كلها بوحدات 100.
    """
    side = str(broker_pos.get("side", "buy")).lower()
    ts = 1 if side == "buy" else 2
    return types.SimpleNamespace(
        positionId=broker_pos.get("ticket"),
        price=broker_pos.get("open_price"),
        digits=2,
        tradeData=types.SimpleNamespace(
            volume=100,
            tradeSide=ts,
        ),
        commission=float(broker_pos.get("commission") or 0.0),
        swap=float(broker_pos.get("swap") or 0.0),
    )


def _st_pos_from_state(state, create=False):
    """يرجع state.position كقيمة dict موحّدة.

    create=False: ترجع القيمة كما هي (قد تكون None) دون تعديل الحالة —
    مهم في مرحلة الفتح حيث يشترط run_trade_cycle أن تكون state.position
    None خلال كل دورتك (تحويلها إلى {} كان يمنع الفتح دائماً).
    create=True تُنشئ {} وتخزنها (تُستخدم في مرحلة الصفقات المفتوحة فقط).
    """
    sp = state.get("position")
    if not isinstance(sp, dict):
        if create:
            sp = {}
            state["position"] = sp
        else:
            return None
    return sp


# ============================================================================
# قرار الفتح — يعيد بناء شروط main.run_trade_cycle حرفياً
# ============================================================================

def _entry_decision(state, result, stats):
    """يبني catch_up + https://flter الثلاث دورات + can_trade summary.

    نفس المعادلات في main.run_trade_cycle (سطر 1408-1524) تمت إعادة
    إنتاجها هنا لأننا لا نشغّل تلك الدالة (تعتمد على reactor). تُرجع
    (can_open: bool, reason: str, side: str|None, catch_up: float,
     trend_against: bool).
    """
    now_ts = _now_unix()
    momentum = result.get("momentum", 0.0)
    plat_mom = result.get("platform_momentum", 0.0)
    catch_up = momentum - plat_mom

    # تهيئة علم الاتجاه
    trend = result.get("trend_slope", 0.0)
    slope_against = (trend * catch_up) < 0
    trend_against = (
        config.TREND_ON and slope_against
        and abs(trend) > config.TREND_MAX_SLOPE_USD
    )

    # السبريد/عمولة للغطاء
    _live_spread = _detected_spread_usd(result)
    _est_fees = _live_spread + _main._commission_usd(None, state=state) \
        if _live_spread > 0 else 0.0

    # تأكيد دورة سابقة (2026-09-29: تأكيد الدورتين → دورتان سابقتان
    # كانتا تشترطان إشارتين كاملتين فوق العتبة، ما قتل أغلب المدخلات؛
    # الآن تكتفي بدورة سابقة واحدة بنفس الاتجاه وفوق العتبة).
    _prev = state.get("_prev_catch_up")
    _confirm_ok = (
        _prev is not None
        and (_prev * catch_up) >= 0
        and abs(_prev) >= config.MOMENTUM_MIN_USD
    )
    state["_prev_catch_up"] = catch_up

    _efloor = _main._entry_floor()
    signal_ready = (
        config.MOMENTUM_ON
        and abs(catch_up) >= _efloor
        and abs(momentum) >= 0.5 * _efloor
        and (momentum * plat_mom) >= 0
        and abs(catch_up) > (_est_fees * 2.0)
        and _confirm_ok
    )

    # حارس السبريد
    spread_wide = (
        config.SPREAD_GUARD_USD > 0
        and _live_spread >= config.SPREAD_GUARD_USD
    )

    # حارس الخسارة نفس الاتجاه
    same_side_blocked = False
    _cside = "SELL" if catch_up < 0 else "BUY"
    _closes = state.get("closed_trades") or []
    if _closes:
        _last = _closes[-1]
        _lp0 = _last.get("pnl_net_usd")
        if _lp0 is None:
            _lp0 = _last.get("pnl_usd", 0.0)
        _ep, _cp = _last.get("entry_price") or 0.0, _last.get("close_price") or 0.0
        _ts = _last.get("ts_close") or _last.get("closed_at")
        if (_lp0 or 0) < 0 and _ep and _cp and _ts:
            _last_side = "BUY" if _cp > _ep else "SELL"
            try:
                _close_dt = datetime.fromisoformat(str(_ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                _close_dt = None
            if (_last_side == _cside and _close_dt is not None
                    and time.time() - _close_dt.timestamp()
                    < config.SAME_SIDE_LOSS_GUARD_MIN * 60.0):
                same_side_blocked = (
                    abs(catch_up) < config.MOMENTUM_MIN_USD
                    * config.SAME_SIDE_LOSS_STRONG_MULT
                )

    cooldown_left = state.get("cooldown_until", 0) - now_ts
    in_session_now = _main.in_session(datetime.now(timezone.utc))
    quality_session_now = _main.in_quality_session(datetime.now(timezone.utc))

    can_open = (
        config.MODE == "trade"
        and stats is not None
        and signal_ready
        and not _main._skip_signal()
        and not spread_wide
        and result.get("balance_usd", 0) >= config.MIN_BALANCE_TO_TRADE
        and cooldown_left <= 0
        and in_session_now
        and quality_session_now
        and result.get("platform_jump", 0.0) < config.PRICE_JUMP_ANOMALY_USD
        and not trend_against
        and not same_side_blocked
        and state.get("position") is None
    )
    reason = None
    if not can_open:
        reason = (
            "pause_open" if config.PAUSE_OPEN else
            "session_blocked" if not quality_session_now else
            "out_session" if not in_session_now else
            "same_side_loss" if same_side_blocked else
            "spread_wide" if spread_wide else
            "cooldown" if cooldown_left > 0 else
            "trend_against" if trend_against else
            "signal_not_ready" if not signal_ready else
            "balance_low" if result.get("balance_usd", 0) < config.MIN_BALANCE_TO_TRADE else
            "not_ready"
        )
    side = "SELL" if catch_up < 0 else "BUY"
    return can_open, reason, side, catch_up, trend_against


# ============================================================================
# دورة التداول
# ============================================================================

def mt5_run_cycle(state, rows, sess):
    """دورة واحدة: إغلاق+فتح — متزامنة، ترجع result dict."""
    result = {"ts": utcnow_iso()}

    # --- حلقة التطوير الذاتي (AI_ON): توصية العقل على الـ entry threshold ---
    # تُطبَّق في الذاكرة على config فقط (لا ملفات/commit)، وبصد قيم شاذة،
    # وفي حدود مفاتيح AI_APPLY_ON / AI_MOMENTUM_MIN_{MIN,MAX}.
    try:
        _main.ai_self_tune(state)
    except Exception as _exc:
        print(f"ai self-tune warn: {_exc!r}", flush=True)

    # --- عقل LLM: تحليل مجدول + خطة + توصيات (كتب تلقائي الخطة كل 6 ساعات) ---
    try:
        import ai_brain
        if ai_brain.AI_ON and ai_brain._needs_run(state):
            _pres = ai_brain.run(state)
            print(f"ai-brain: {_pres}", flush=True)
    except Exception as _exc:
        print(f"ai-brain warn: {_exc!r}", flush=True)

    # --- إحصائيات من rows (platform mid فقط) ---
    stats = _main.compute_stats(rows, verbose=False)

    mid = None
    tk = sess.tick()
    if tk:
        mid = (tk["bid"] + tk["ask"]) / 2.0
    if mid is None and stats:
        mid = stats.get("mean")
    if mid is None:
        result["action"] = "hold:no_mid"
        return result
    # حارس النطاق 2026-09-29: بداية الدورة بعد boot يرجع الصف الأول
    # أحياناً tick غير ناضج (مثال حي 1825 بدل 4115) — نفترضه خلل بيانات
    # ولا نكمّل به (لا فتح/إغلاق، ولا إلحاق التاريخ).
    if not (config.MIN_PLATFORM_PRICE <= mid <= config.MAX_PLATFORM_PRICE):
        result["action"] = "hold:out_of_range"
        result["mid"] = round(mid, 2)
        return result
    result["mid"] = mid

    # global price (ياهو GC=F القائد) — نفس مصدر live.py
    global_price = None
    try:
        gp_price, gp_src, gp_ts = gold_price.get_global_gold_price()
        global_price = float(gp_price)
    except Exception as exc:
        print(f"gold_price warn: {exc!r}", flush=True)
    if global_price is None:
        global_price = mid
    result["global_price"] = global_price
    result["gap"] = mid - global_price
    result["gold_src"] = gp_src if (gp_price is not None) else "mid-fallback"

    # --- نلحق صفاً حياً بالتاريخ (mid + global) قبل حساب المومنتوم ---
    # (الدورة قصيرة على Actions؛ بناء rows حي هو ما يجعل الزخم يعمل)
    rows.append({
        "ts": utcnow_iso(),
        "global": global_price,
        "platform": mid,
        "gap": round(mid - global_price, 2),
    })
    _max_rows = getattr(config, "MAX_HISTORY_ROWS", 2000) or 2000
    if len(rows) > _max_rows:
        del rows[:-_max_rows]
    _main.save_history(rows)

    # --- مومنتومات (من rows — نفس windows) ---
    result["trend_slope"] = _main.trend_slope(rows)
    result["momentum"] = _main.yahoo_momentum(rows)
    result["platform_momentum"] = _main.platform_momentum(rows)
    result["platform_jump"] = abs(result["platform_momentum"])
    result["catch_up"] = result["momentum"] - result["platform_momentum"]

    # السبريد الحي (bid→ask من MT5 نفسها)
    if tk:
        result["spread_usd"] = round(tk["ask"] - tk["bid"], 2)
    # يُخزَّن في state حتى تستخدمه طبقات الإغلاق (التريلنج/الأرباح) —
    # التكلفة الحي بدل التقدير الثابت (القاعدة 3ب).
    if result.get("spread_usd"):
        state["_last_spread_usd"] = result["spread_usd"]

    result["balance_usd"] = 0.0
    acc = sess.account_info()
    if acc:
        result["balance_usd"] = float(acc.get("equity") or acc.get("balance") or 0.0)

    # --- موضع الوسيط الفعلي (MT5 يقوّى) ---
    broker_pos = None
    try:
        for _p in (sess.positions_get() or []):
            if _p["symbol"] == config.SYMBOL:
                broker_pos = _p
                break
    except Exception as exc:
        print(f"positions_get warn: {exc!r}", flush=True)
    result["open_positions"] = 1 if broker_pos else 0

    state_pos = _st_pos_from_state(state, create=False)
    closing_mgr = _main.ClosingManager(state, config)
    closing_mgr.init_from_state(state)

    # ============ مرحلة الإغلاق ============
    if broker_pos is not None:
        pos_ns = _pos_ns(broker_pos)
        st_pos = _st_pos_from_state(state, create=True) or state.get("position") or {}
        st_pos["positionId"] = broker_pos["ticket"]
        st_pos["side"] = "SELL" if broker_pos["side"] == "sell" else "BUY"
        st_pos["entry_price"] = st_pos.get("entry_price") or broker_pos["open_price"]
        st_pos.setdefault("opened_at", utcnow_iso())
        st_pos.setdefault("pnl_peak_usd", 0.0)
        st_pos.setdefault("pnl_track", [])
        state["_anomaly_jump"] = result["platform_jump"]

        should_close, close_reason = closing_mgr.check_close(
            pos_ns, mid, global_price, stats, st_pos, _now_unix(),
            state.get("money_digits") or 2,
        )
        result["close_check"] = {"should_close": should_close,
                                 "reason": close_reason}
        if should_close and close_reason:
            # تأخير بشري للإغلاق الاختياري فقط — الأمان فوراً
            if (close_reason in ("trailing", "profit_target", "z_revert",
                                 "giveback", "no_progress")
                    and config.HUMANIZE_ON):
                half = _main._human_reaction() / 2.0
                if half > 0:
                    time.sleep(half)
            ok, msg = sess.close_position(
                symbol=config.SYMBOL, side=broker_pos["side"],
                volume=even_volume(config.LOT),
            )
            if ok:
                state["position"] = None
                state["cooldown_until"] = _now_unix() + \
                    _human_cooldown()
                pnl_net = 0.0
                entry_p = st_pos.get("entry_price")
                if entry_p:
                    price_diff = mid - entry_p
                    if st_pos["side"] == "SELL":
                        price_diff = -price_diff
                    gross = price_diff * 100 / 100.0  # md=2, volume=100
                    fees = _main.position_fees_usd(
                        pos_ns, 2, result=result, state=state)
                    pnl_net = round(gross - fees, 2)
                if pnl_net > 0:
                    closing_mgr.record_win(pnl_net)
                else:
                    closing_mgr.record_loss(pnl_net)
                closing_mgr.save_perf_to_state(state)
                _main._record_close(state, {
                    "ts_open": st_pos.get("opened_at"),
                    "ts_close": utcnow_iso(),
                    "side": st_pos["side"],
                    "entry_gap": st_pos.get("entry_gap"),
                    "close_gap": result["gap"],
                    "entry_price": entry_p,
                    "close_price": mid,
                    "pnl_units": pnl_net,
                    "pnl_usd": pnl_net,
                    "fees_usd": round(fees, 2),
                    "spread_usd": round(_detected_spread_usd(result), 2),
                    "pnl_net_usd": pnl_net,
                    "reason": close_reason,
                    "pnl_peak_usd": round(float(st_pos.get("pnl_peak_usd") or 0), 2),
                })
                result["action"] = "close:" + close_reason
                result["close_pnl_usd"] = pnl_net
            else:
                # قد يكون الوسيط أغلقها (ستوب/هدف خارجي)
                if "position not found" in (msg or "").lower():
                    pnl_ext = 0.0
                    f_ext = 0.0
                    entry_p = st_pos.get("entry_price")
                    hit = "sl_hit"
                    close_price = mid
                    # الحقيقة من سجل الصفقات: إغلاق الوسيط (stop/TP) تحته
                    # deal محفوظ عند السيرفر — profit الفعلي والسبب (4=stop,
                    # 5=target، comment "[sl …]"/"[tp …]") لا التخمين من mid.
                    try:
                        _deals = sess.history_deals_get(
                            symbol=config.SYMBOL,
                            position_id=int(st_pos.get("positionId") or 0),
                        )
                        for _d in (_deals or []):
                            if int(_d.get("entry", 0)) == 1:
                                pnl_ext = round(float(_d.get("profit") or 0.0)
                                                + float(_d.get("commission") or 0.0)
                                                + float(_d.get("swap") or 0.0)
                                                + float(_d.get("fee") or 0.0), 2)
                                f_ext = round(float(_d.get("commission") or 0.0)
                                              + float(_d.get("swap") or 0.0)
                                              + float(_d.get("fee") or 0.0), 2)
                                if _d.get("price"):
                                    close_price = float(_d["price"])
                                hit = "tp_hit" if pnl_ext > 0 else "sl_hit"
                                _c = str(_d.get("comment") or "")
                                if "[tp" in _c or "[TP" in _c:
                                    hit = "tp_hit"
                                elif "[sl" in _c or "[SL" in _c:
                                    hit = "sl_hit"
                                break
                    except Exception as exc:
                        print(f"history deals ext warn: {exc!r}", flush=True)
                    if not entry_p:
                        entry_p = st_pos.get("entry_price")
                    side_n = st_pos.get("side") or broker_pos["side"]
                    if pnl_ext > 0:
                        closing_mgr.record_win(pnl_ext)
                    else:
                        closing_mgr.record_loss(pnl_ext)
                    state["position"] = None
                    state["cooldown_until"] = _now_unix() + _human_cooldown()
                    _main._record_close(state, {
                        "ts_open": st_pos.get("opened_at"),
                        "ts_close": utcnow_iso(),
                        "side": side_n,
                        "entry_gap": st_pos.get("entry_gap"),
                        "close_gap": result["gap"],
                        "entry_price": entry_p,
                        "close_price": close_price,
                        "pnl_units": pnl_ext,
                        "pnl_usd": pnl_ext,
                        "fees_usd": round(f_ext, 2),
                        "spread_usd": round(_detected_spread_usd(result), 2),
                        "pnl_net_usd": pnl_ext,
                        "reason": hit,
                        "pnl_peak_usd": round(float(st_pos.get("pnl_peak_usd") or 0), 2),
                    })
                    closing_mgr.save_perf_to_state(state)
                    result["action"] = "close:external-reconciled"
                    result["close_pnl_usd"] = pnl_ext
                    result["close_reason_ext"] = hit
                else:
                    result["action"] = "close_pending"
                    result["close_error"] = msg
        else:
            st_pos["pnl_peak_usd"] = round(_pos_peak(state, st_pos, mid, result), 2)
            result["action"] = "hold"
        return result

    # ============ مرحلة الفتح ============
    # موضع في الحالة المحلية لكن لا موضع عند الوسيط = إغلاق خارجي
    if state_pos is not None and state_pos.get("positionId"):
        pnl_ext = 0.0
        f_ext = 0.0
        entry_p = state_pos.get("entry_price")
        side_n = state_pos.get("side") or "BUY"
        hit = "sl_hit"
        close_price = mid
        try:
            _deals = sess.history_deals_get(
                symbol=config.SYMBOL,
                position_id=int(state_pos.get("positionId") or 0),
            )
            for _d in (_deals or []):
                if int(_d.get("entry", 0)) == 1:
                    pnl_ext = round(float(_d.get("profit") or 0.0)
                                    + float(_d.get("commission") or 0.0)
                                    + float(_d.get("swap") or 0.0)
                                    + float(_d.get("fee") or 0.0), 2)
                    f_ext = round(float(_d.get("commission") or 0.0)
                                  + float(_d.get("swap") or 0.0)
                                  + float(_d.get("fee") or 0.0), 2)
                    if _d.get("price"):
                        close_price = float(_d["price"])
                    hit = "tp_hit" if pnl_ext > 0 else "sl_hit"
                    _c = str(_d.get("comment") or "")
                    if "[tp" in _c or "[TP" in _c:
                        hit = "tp_hit"
                    elif "[sl" in _c or "[SL" in _c:
                        hit = "sl_hit"
                    break
        except Exception as exc:
            print(f"history deals ext2 warn: {exc!r}", flush=True)
        if not entry_p:
            entry_p = state_pos.get("entry_price")
        if pnl_ext > 0:
            closing_mgr.record_win(pnl_ext)
        else:
            closing_mgr.record_loss(pnl_ext)
        state["position"] = None
        state["cooldown_until"] = _now_unix() + _human_cooldown()
        _main._record_close(state, {
            "ts_open": state_pos.get("opened_at"),
            "ts_close": utcnow_iso(),
            "side": side_n,
            "entry_gap": state_pos.get("entry_gap"),
            "close_gap": result["gap"],
            "entry_price": entry_p,
            "close_price": close_price,
            "pnl_units": pnl_ext,
            "pnl_usd": pnl_ext,
            "fees_usd": round(f_ext, 2),
            "spread_usd": round(_detected_spread_usd(result), 2),
            "pnl_net_usd": pnl_ext,
            "reason": hit,
            "pnl_peak_usd": round(float(state_pos.get("pnl_peak_usd") or 0), 2),
        })
        closing_mgr.save_perf_to_state(state)
        result["action"] = "close:external-reconciled"
        result["close_pnl_usd"] = pnl_ext
        result["close_reason_ext"] = hit
        return result

    can_open, reason, side, catch_up, _ta = _entry_decision(
        state, result, stats)
    if not can_open:
        result["action"] = "hold:" + (reason or "not_ready")
        return result

    # --- منع التعدد الصارم 2026-09-22: فحص الوسيط الفعلي قبل الفتح ---
    # لا نعتمد على الحالة المحلية فقط — نقرأ MT5 حياً: أي positionId
    # نشط للرمز يمنع الفتح مهما حدث للحالة (broker_open_position_ids).
    try:
        live_open = sess.broker_open_position_ids(config.SYMBOL)
    except Exception as exc:
        print(f"broker open ids warn: {exc!r}", flush=True)
        live_open = []
    if live_open:
        result["action"] = "hold:broker_already_open"
        result["open_positions"] = len(live_open)
        return result

    # --- التكلفة الفعلية (سبريد حي + عمولة) تُدخل في مسافة SL/TP ---
    # الهدف: صافي التعبير عند SL/TP = الحد المطلوب بعد خصم التكلفة.
    _live_spread = _detected_spread_usd(result)
    _fees = _live_spread + _main._commission_usd(None, state=state)
    if _live_spread <= 0:
        _fees = 0.0

    # OK — فتح صفقة
    tk2 = sess.tick()
    if not tk2:
        result["action"] = "hold:no_tick"
        return result
    entry = tk2["ask"] if side == "BUY" else tk2["bid"]

    # SL: مسافة أساسية SL_AFTER_ENTRY_USD (صافي الخسارة يبقى على الحد
    # بعد العمولة/السبريد لأنها تُخصم من الطرف الآخر). التشتت البشري
    # يُطبَّق على الأساس نفسه كما في main.
    sl_base = max(1.0, config.SL_AFTER_ENTRY_USD - _fees) if _fees else \
        config.SL_AFTER_ENTRY_USD
    sl_dist = _main._jitter_usd(sl_base, config.HUMAN_SL_TP_JITTER_USD)

    # TP: الحد الأدنى يشمل التكلفة بحيث صافي الربح ≥ PROFIT_TARGET بعد
    # خصمها — ربح حقيقي لا اسمي. (0.50×|catch_up| يبقى منطق اللحاق نفسه.)
    # 2026-10-01: 1.40 → 1.60 (الحد الأدنى على TF كي لا تُفتح صفقات هامشية
    # يتلاشى صافيها بعد العمولة/السبريد). تشتت بشري ثابت لكل صفقة يعزل
    # قيم TP الحرفية المتطابقة — يُبنى من لقطة واصلة عشوائية قبل الفتح
    # (لا positionId بعد) عبر _stable_jitter.
    _tp_seed = f"tp-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}-{int(time.time()*1000) % 997}"
    _tp_jit = _main._stable_jitter(_tp_seed, 0.04)
    min_tp_dist = max(1.60, config.PROFIT_TARGET_USD * (1.0 + _tp_jit)) + _fees
    tp_ext = max(min_tp_dist, 0.50 * abs(catch_up))
    if side == "SELL":
        sl = entry + sl_dist
        tp = entry - tp_ext
    else:
        sl = entry - sl_dist
        tp = entry + tp_ext

    vol = config.LOT
    label = mt5_broker._human_label()
    print(f"order-request side={side} entry={entry:.2f} sl={sl:.2f} "
          f"tp={tp:.2f} catch={catch_up:+.2f} vol={vol} label={label}",
          flush=True)

    # تأخير بشري قبل التنفيذ
    react = _main._human_reaction()
    if react > 0:
        print(f"human-reaction: waiting {react:.1f}s before order", flush=True)
        time.sleep(react)

    ok, msg = sess.open_position(
        symbol=config.SYMBOL, side=side, volume=vol, sl=sl, tp=tp,
        comment="", magic=None,
    )
    if ok:
        state["position"] = {
            "positionId": str(ok),
            "side": side,
            "entry_gap": result["gap"],
            "entry_price": entry,
            "opened_at": utcnow_iso(),
            "pnl_peak_usd": 0.0,
            "pnl_track": [],
            "stop_loss": round(sl, 4),
            "take_profit": round(tp, 4),
            "sltp_set": True,
            "label": label,
        }
        state["cooldown_until"] = 0
        closing_mgr.trade_count_today += 1
        closing_mgr.save_perf_to_state(state)
        result["action"] = "open:" + side
        result["ticket"] = str(ok)
        result["sl"] = round(sl, 4)
        result["tp"] = round(tp, 4)
    else:
        result["action"] = "open_failed"
        result["open_error"] = msg
    return result


# ============================================================================
# أدوات مساعدة
# ============================================================================

def _pos_peak(state, st_pos, mid, result=None):
    """قمة pnl صافية لحي من mid (لا تُقلل أبداً).

    التكلفة (سبريد حي + عمولة) تُخصم من القيمة الخام حتى تتطابق عتبات
    التريلنج/الأرباح مع الصافي الحقيقي بعد الرسوم (القاعدة 3ب).
    """
    peak = float(st_pos.get("pnl_peak_usd") or 0)
    entry = st_pos.get("entry_price")
    if not entry:
        return round(peak, 2)
    side = st_pos.get("side")
    diff = mid - float(entry)
    if side == "SELL":
        diff = -diff
    net = diff * 100 / 100.0
    fees = _main.position_fees_usd(
        types.SimpleNamespace(commission=0.0, swap=0.0),
        2, result=result, state=state)
    return round(max(peak, net - fees), 2)


def _human_cooldown():
    """تهدئة بشرية مشوّشة ±15% (القاعدة 1)."""
    _cd = config.COOLDOWN_MINUTES * 60
    if config.HUMANIZE_ON:
        import random as _r
        _cd *= _r.uniform(0.85, 1.15)
    return _cd


def even_volume(vol_lots):
    """يوحَّد حجم الإغلاق بنفس دقة الفتح (0.01 لوت)."""
    return round(max(0.01, float(vol_lots)), 2)


def mt5_probe():
    """فحص تمهيدي آمن (MT5_PROBE=1): اتصال + حساب + رمز + سبريد حي.

    لا يفتح أي صفقة إطلاقاً — فقط يتحقق من أن الرمز الهدف (XAUUSD أو
    لاحقته) موجود وقابل للتداول وسبريده معقول، قبل أي تشغيل تنفيذي.
    يرجع 0 عند النجاح و1 عند الفشل (مخرج عملية).
    """
    ok, err = mt5_broker.initialize(
        login=os.environ.get("MT5_LOGIN") or None,
        password=os.environ.get("MT5_PASSWORD") or None,
        server=os.environ.get("MT5_SERVER") or None,
        path=(os.environ.get("MT5_TERMINAL_PATH")
              or os.environ.get("MT5_PATH") or None),
    )
    if not ok:
        print(f"mt5 probe: initialize failed: {err}", flush=True)
        return 1
    acc = mt5_broker.account_info()
    if acc:
        print("mt5 probe: account:", json.dumps(acc, ensure_ascii=False),
              flush=True)
    else:
        print("mt5 probe: no account_info", flush=True)

    wanted = os.environ.get("MT5_SYMBOL") or config.MT5_SYMBOL
    print("mt5 probe: probing symbol:", wanted, flush=True)
    info = mt5_broker.symbol_properties(wanted)
    if info is None:
        # اكتشاف حي: جرّب أصناف XAUUSD الشائعة إن لم يوجد الرمز المطلوب
        for cand in ("XAUUSD", "XAUUSD.a", "XAUUSDm", "XAUUSD.r", "Gold"):
            found = mt5_broker.symbol_properties(cand)
            if found is not None:
                info = found
                print("mt5 probe: resolved symbol ->", cand, flush=True)
                break
    if info is None:
        print("mt5 probe: no tradable gold symbol found", flush=True)
        mt5_broker.shutdown()
        return 1
    print("mt5 probe: symbol:", json.dumps(info, ensure_ascii=False),
          flush=True)

    t = mt5_broker.tick(info["symbol"])
    bid = (t or {}).get("bid")
    ask = (t or {}).get("ask")
    spread = round(ask - bid, 2) if (bid is not None and ask) else None
    print(f"mt5 probe: bid={bid} ask={ask} spread_usd={spread}",
          flush=True)
    if spread is None or spread > config.SPREAD_GUARD_USD:
        print(f"mt5 probe: spread {spread} exceeds SPREAD_GUARD "
              f"({config.SPREAD_GUARD_USD:.2f})", flush=True)
    mt5_broker.shutdown()
    return 0


# ============================================================================
# الدخول الرئيسي — دورة قصيرة (GitHub Actions)
# ============================================================================

def mt5_run_duration(duration_min=0.0):
    """تشغيل حتى انتهاء المدة أو جولة واحدة (duration_min=0)."""
    state = _load_state()
    rows = _main.load_history()

    ok, err = mt5_broker.initialize(
        login=os.environ.get("MT5_LOGIN") or None,
        password=os.environ.get("MT5_PASSWORD") or None,
        server=os.environ.get("MT5_SERVER") or None,
        path=(os.environ.get("MT5_TERMINAL_PATH")
              or os.environ.get("MT5_PATH") or None),
    )
    if not ok:
        print(f"mt5 initialize failed: {err}", flush=True)
        return 1

    sess = mt5_broker
    acc = sess.account_info()
    if acc:
        print(f"mt5 account: login={acc.get('login')} "
              f"server={acc.get('server')} balance={acc.get('balance')}",
              flush=True)

    t0 = _now_unix()
    deadline = (t0 + duration_min * 60.0) if duration_min and duration_min > 0 \
        else None
    iterations = 0
    while True:
        iterations += 1
        try:
            result = mt5_run_cycle(state, rows, sess)
            print(f"[{utcnow_iso()}] {json.dumps(result, ensure_ascii=False)}",
                  flush=True)
        except Exception as exc:
            import traceback
            print(f"[{utcnow_iso()}] cycle error: "
                  f"{traceback.format_exc(limit=20)}", flush=True)
        _main.save_history(rows)
        # day reset داخل init_from_state
        _save_state(state)
        if deadline is not None and _now_unix() >= deadline:
            break
        if not deadline:
            break
        # جرد بشري مشوّش — قصير چون الدورة قصيرة على Actions
        import random as _r
        wait = max(1.0, (_main._poll_jitter() + _r.uniform(-1, 1)))
        print(f"[{utcnow_iso()}] sleep {wait:.1f}s", flush=True)
        time.sleep(min(wait, 60.0))

    mt5_broker.shutdown()
    return 0


if __name__ == "__main__":
    import os as _os
    if (_os.environ.get("MT5_PROBE") or "0") == "1":
        raise SystemExit(mt5_probe())
    raise SystemExit(mt5_run_duration(
        duration_min=float(_os.environ.get("MT5_DURATION_MIN", 0.0))))