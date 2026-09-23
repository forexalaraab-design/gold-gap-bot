#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
strategy.py — نموذج الإشارة لنسخة v2 (2026-09-23).

يبني قرار الفتح والخروج من أخطاء 200 صفقة حية لنسخة v1:
  1. الخسارة المحققة كانت تفوق العتبة دائماً (-2.24/-2.75 عند سقف 2.0)
     بسبب الانزلاق والرسوم → محرض أبكر (V2_RISK_PER_TRADE_USD) بحيث
     يبقى المحقق فعلياً قرب الحد × 1.1 (بدل × 1.4).
  2. الربح كان أصغر من الخسارة (R:R < 1) → TP ≥ V2_TP_RISK_RATIO × المخاطرة.
  3. خسائر راكدة في ساعات اليوم وعطلات اللحاق → غربلة الساعات الموجبة
     + اشتراط حركة حية |platform_momentum| ≥ حد أدنى.
  4. دورات المحاولات الميتة المتكررة → حد يومي + قبول إشارة واحدة فقط.

الوحدة لا تتصل بالبروكر إطلاقاً؛ تدير فقط القرار وسجل التقييم الافتراضي
(data/v2_virtual.csv) الذي يتغذى بأسعار mid الحية من نفس الدورة.
"""

import csv
import os
import time

try:
    import config as _cfg

    DEFAULT_CONFIG = _cfg
except Exception:  # pragma: no cover
    DEFAULT_CONFIG = None

from datetime import datetime, timezone


def _utc_hour(now=None):
    if isinstance(now, int):
        return now % 24
    return datetime.now(timezone.utc).hour


def _utc_iso(ts=None):
    ts = time.time() if ts is None else ts
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


def _side_from_catch(catch_up):
    return "SELL" if catch_up < 0 else "BUY"


def _today(dt_ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime(dt_ts))


def _today_net(state):
    d = state.get("_v2_daily") or {}
    return float(d.get(_today(), 0.0))


def _add_net(state, net):
    d = state.get("_v2_daily") or {}
    d[_today()] = round(d.get(_today(), 0.0) + float(net), 2)
    state["_v2_daily"] = d


def v2_decision(config, *, catch_up, momentum, plat_mom, spread_usd,
                fees_usd, state, mid=None, side_hint=None, now_hour=None):
    """قرار الفتح وفق نموذج v2. يرجع:
    {"approved": bool, "reason": str, "meta": dict|None}.
    meta عند القبول: side/sl_dist/tp_dist/risk_usd/tp_usd (كلها صافية).
    لا يتصل بأي مصدر خارجي ولا يُرسل شيئاً للبروكر.
    """
    reason = None
    hour = _utc_hour(now_hour)
    if config.V2_SESSION_HOURS_ON and hour not in config.V2_POSITIVE_HOURS:
        reason = "hour"
    elif not catch_up or abs(catch_up) < config.MOMENTUM_MIN_USD:
        reason = "catchup"
    elif fees_usd and abs(catch_up) <= float(fees_usd) * 2.0:
        reason = "fees"
    elif spread_usd is None or spread_usd < 0 or \
            spread_usd > config.V2_MAX_SPREAD_USD:
        reason = "spread"
    elif plat_mom is None or abs(plat_mom) < config.V2_MIN_PLAT_MOMENTUM:
        reason = "stale"
    elif (momentum * plat_mom) < 0:
        reason = "conflict"
    if reason is not None:
        return {"approved": False, "reason": reason, "meta": None}

    side = side_hint or _side_from_catch(catch_up)
    # حد يومي صارم: لا نسمح أن تكون الصفقة التالية سبب تبليغ حد اليوم.
    if _today_net(state) - config.V2_RISK_PER_TRADE_USD <= \
            -config.V2_DAILY_MAX_LOSS_USD:
        return {"approved": False, "reason": "daily", "meta": None}

    risk = config.V2_RISK_PER_TRADE_USD
    tp = max(config.V2_TP_MIN_USD,
             config.V2_RISK_PER_TRADE_USD * config.V2_TP_RISK_RATIO)
    return {
        "approved": True,
        "reason": "ok",
        "meta": {
            "side": side,
            "sl_dist": risk,
            "tp_dist": tp,
            "risk_usd": risk,
            "tp_usd": tp,
        },
    }


def _virtual_gross(v, mid):
    diff = float(mid) - float(v["mid"])
    if v["side"] == "SELL":
        diff = -diff
    return diff


def _append_csv(path, row):
    try:
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        new_file = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow([
                    "ts_open", "ts_close", "side", "entry_mid", "exit_mid",
                    "gross_usd", "fees_usd", "net_usd", "reason", "hour",
                    "catch_up", "risk_usd", "tp_usd",
                ])
            w.writerow(row)
    except Exception:
        pass


def _v2_close(state, config, v, mid, net, reason):
    row = [
        v.get("ts_iso"), _utc_iso(), v.get("side"),
        round(float(v["mid"]), 2), round(float(mid), 2),
        round(float(net) + float(v.get("fees_usd") or 0.0), 2),
        round(float(v.get("fees_usd") or 0.0), 2),
        round(float(net), 2), reason, v.get("hour"),
        round(float(v.get("catch_up", 0.0)), 2),
        round(float(v.get("risk_usd", 0.0)), 2),
        round(float(v.get("tp_usd", 0.0)), 2),
    ]
    _append_csv(config.V2_VIRTUAL_FILE, row)
    _add_net(state, net)
    state["_v2_virtual"] = None
    print(f"[v2-virtual] CLOSED {reason}: net={net:.2f}", flush=True)


def virtual_step(state, config, mid, catch_up, momentum, plat_mom,
                 spread_usd, fees_usd, signal_ok=False, live_busy=False):
    """يحاكي صفقات v2 افتراضياً على mid الحي بلا أي طلب للوسيط.

    عند وجود صفقة افتراضية مفتوحة: تحديث PnL وإغلاق عند المخاطرة/الهدف/
    سقف المدة. عند فراغها وإشارة صالحة وعدم انشغال صفقة حية: فتحها
    وفق v2_decision. السجل يُلحق بـ config.V2_VIRTUAL_FILE.
    """
    if live_busy:
        return
    v = state.get("_v2_virtual")
    now_hour = _utc_hour()
    if v:
        gross = _virtual_gross(v, mid)
        fees = float(v.get("fees_usd") or 0.0)
        net = gross - fees
        v["peak_net"] = max(float(v.get("peak_net", 0.0)), net)
        age_sec = time.time() - float(v.get("_ts", 0.0))
        reason = None
        if net <= -float(v["risk_usd"]):
            reason = "max_loss_v2"
        elif net >= float(v["tp_usd"]):
            reason = "profit_target_v2"
        elif age_sec >= config.MAX_HOLD_HOURS * 3600:
            reason = "max_hold_v2"
        if reason:
            _v2_close(state, config, v, mid, net, reason)
        else:
            state["_v2_virtual"] = v
        return
    if not signal_ok:
        return
    dec = v2_decision(
        config, catch_up=catch_up, momentum=momentum, plat_mom=plat_mom,
        spread_usd=spread_usd, fees_usd=fees_usd, state=state, mid=mid,
        side_hint=_side_from_catch(catch_up), now_hour=now_hour,
    )
    if not dec["approved"]:
        return
    m = dec["meta"]
    state["_v2_virtual"] = {
        "side": m["side"],
        "mid": float(mid),
        "_ts": time.time(),
        "ts_iso": _utc_iso(),
        "hour": now_hour,
        "catch_up": float(catch_up),
        "risk_usd": float(m["risk_usd"]),
        "tp_usd": float(m["tp_usd"]),
        "fees_usd": float(fees_usd or 0.0),
        "peak_net": 0.0,
    }


if DEFAULT_CONFIG is not None:
    # تحقق سريع عند الاستيراد من سطر أوامر (بيانات محلية، لا شبكة)
    _sample = v2_decision(
        DEFAULT_CONFIG,
        catch_up=2.0,
        momentum=1.6,
        plat_mom=1.1,
        spread_usd=0.12,
        fees_usd=0.15,
        state={},
        mid=4300.0,
        now_hour=14,
    )
    assert _sample["approved"] is True, _sample