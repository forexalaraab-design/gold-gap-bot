# -*- coding: utf-8 -*-
"""
multi_bot/executor.py — تنفيذ الصفقات عبر MT5
"""
import os
import time
import json
from datetime import datetime, timezone

from multi_bot import config, guard


def _mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None


def initialize(retries=6, delay=8.0):
    """
    2026-10-29: اتصال مقاوم للسحابة — إعادة محاولة + تسجيل دخول صريح + تشخيص.
    التيرمنال في الـ runner يُقلع للتو، فأول `initialize` قد ينجح قبل أن يتصل.
    """
    mt5 = _mt5()
    if mt5 is None:
        return False, "MetaTrader5 not installed"
    path = getattr(config, "MT5_PATH", "") or os.environ.get("MT5_TERMINAL_PATH", "")
    have_path = bool(path and os.path.exists(path))
    last = "no attempt"
    for attempt in range(1, int(retries) + 1):
        try:
            info = mt5.terminal_info()
            if info is None:
                if have_path:
                    ok = mt5.initialize(path, login=config.MT5_LOGIN,
                                        password=config.MT5_PASSWORD, server=config.MT5_SERVER)
                else:
                    ok = mt5.initialize()
                if not ok:
                    last = f"initialize failed: {mt5.last_error()}"
                    print(f"[mt5] attempt {attempt}: {last}", flush=True)
                    time.sleep(delay)
                    continue
            info = mt5.terminal_info()
            if info is None:
                last = "terminal_info None"
                time.sleep(delay)
                continue
            if not getattr(info, "connected", False):
                last = "terminal not connected"
                if config.MT5_LOGIN:
                    try:
                        mt5.login(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
                    except Exception as exc:
                        last = f"login error: {type(exc).__name__}"
                print(f"[mt5] attempt {attempt}: {last}", flush=True)
                time.sleep(delay)
                continue
            acc = mt5.account_info()
            if acc is None:
                last = "account_info None (not logged in)"
                if config.MT5_LOGIN:
                    try:
                        mt5.login(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
                    except Exception as exc:
                        last = f"login error: {type(exc).__name__}"
                time.sleep(delay)
                continue
            print(f"[mt5] connected attempt={attempt} path={path or 'default'} "
                  f"login={getattr(acc, 'login', '?')} server={getattr(acc, 'server', '?')} "
                  f"equity={getattr(acc, 'equity', 0):.2f}", flush=True)
            return True, "connected"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            print(f"[mt5] attempt {attempt}: {last}", flush=True)
            time.sleep(delay)
    return False, last


def shutdown():
    mt5 = _mt5()
    if mt5:
        try:
            mt5.shutdown()
        except Exception:
            pass


def _prepare(symbol, side, lots, sl, tp):
    """
    يبني الطلب **بنفس الشيفرة** المستخدمة في التنفيذ الحقيقي، بلا إرسال.
    الفصل مقصود: الفحص الجاف يجب أن يُثبت المسار الحقيقي لا مساراً موازياً.
    """
    mt5 = _mt5()
    if mt5 is None:
        return None, "no mt5"
    sym = (config.MT5_SYMBOL_SUFFIX + symbol).upper()
    try:
        mt5.symbol_select(sym, True)
    except Exception:
        pass
    info = mt5.symbol_info(sym)
    if info is None:
        return None, f"symbol not found: {sym}"
    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return None, f"tick not found: {sym}"
    price = tick.ask if side == "BUY" else tick.bid
    if side == "BUY":
        if float(sl) >= price:
            sl, tp = tp, sl
    elif side == "SELL":
        if float(sl) <= price:
            sl, tp = tp, sl
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(lots),
        "type": order_type,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 10,
        "magic": 20261011,
        "comment": "",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    return {"mt5": mt5, "request": request, "info": info}, "ok"


def check_order(symbol, side, lots, sl, tp):
    """
    فحص جاف: يُرسل الطلب إلى **مدقق الوسيط** (`order_check`) ولا يُنفّذه أبداً.
    لا يوجد `order_send` في هذه الدالة — بلا استثناء.
    """
    prepared, why = _prepare(symbol, side, lots, sl, tp)
    if prepared is None:
        return "prepare_failed", {"error": why}
    mt5, request, info = prepared["mt5"], prepared["request"], prepared["info"]
    if float(lots) > config.MAX_LOT:
        return "lot_cap", {"error": f"{lots}>{config.MAX_LOT}"}
    detail = {
        "symbol": request["symbol"],
        "price": request["price"],
        "sl": request["sl"],
        "tp": request["tp"],
        "volume": request["volume"],
        "digits": getattr(info, "digits", None),
        "stops_level": getattr(info, "trade_stops_level", None),
    }
    try:
        res = mt5.order_check(request)
    except Exception as exc:
        detail["error"] = type(exc).__name__
        return "check_error", detail
    if res is None:
        detail["error"] = str(mt5.last_error())
        return "check_none", detail
    detail.update({
        "retcode": int(getattr(res, "retcode", -1)),
        "comment": getattr(res, "comment", ""),
        "margin": round(float(getattr(res, "margin", 0.0) or 0.0), 2),
        "margin_free": round(float(getattr(res, "margin_free", 0.0) or 0.0), 2),
        "margin_level": round(float(getattr(res, "margin_level", 0.0) or 0.0), 2),
    })
    return ("accepted" if int(detail["retcode"]) == 0 else "rejected"), detail


def open_position(symbol, side, lots, sl, tp):
    mt5 = _mt5()
    if mt5 is None:
        return None, "no mt5"
    # 2026-10-29: حارس **على مستوى الحساب كله** من حقيقة الوسيط.
    # القديم كان يفحص الرمز نفسه عبر positions_get() على تيرمنال يُقلع للتو
    # فيرجع فارغاً ⇒ 129 صفقة مفتوحة في وقت واحد.
    if float(lots) > config.MAX_LOT:
        return None, f"lot_cap:{config.MAX_LOT}"

    prepared, why = _prepare(symbol, side, lots, sl, tp)
    if prepared is None:
        return None, why
    mt5, request = prepared["mt5"], prepared["request"]
    sym = request["symbol"]
    sl, tp = request["sl"], request["tp"]

    # 2026-10-29: طبقة ثانية للمخاطرة عند التنفيذ (الفحص في scanner قد يسبق حركة سعر)
    from multi_bot.risk import risk_usd
    loss = risk_usd(symbol, request["price"], sl, lots)
    budget = config.MAX_RISK_PCT_PER_TRADE * max(guard.equity(), 0.0)
    if loss is None:
        return None, "risk_unknown"
    if loss > budget:
        return None, f"risk_over_budget:{loss:.2f}>{budget:.2f}"

    # 2026-10-30: عدد الصفقات بلا حدّ، لكن **إجمالي المخاطرة** محدود.
    blocked, why = guard.exposure_gate(symbol, add_risk_usd=loss)
    if blocked:
        return None, f"blocked:{why}"

    result = mt5.order_send(request)
    if result is None:
        return None, f"order_send failed: {mt5.last_error()}"
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return None, f"order rejected: {result.retcode} {result.comment}"
    return {
        "order": result.order,
        "deal": result.deal,
        "volume": result.volume,
        "price": result.price,
        "symbol": sym,
        "side": side,
        "sl": sl,
        "tp": tp,
    }, "ok"


def close_position(order_id=None, symbol=None, side=None, lots=None):
    mt5 = _mt5()
    if mt5 is None:
        return False, "no mt5"
    positions = mt5.positions_get()
    if positions is None:
        return False, "no positions"
    for pos in positions:
        sym = (config.MT5_SYMBOL_SUFFIX + (symbol or "")).upper()
        if symbol and pos.symbol.upper() != sym:
            continue
        if order_id and pos.ticket != order_id:
            continue
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask,
            "deviation": 10,
            "magic": 20261011,
            "comment": "",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return False, f"close failed: {mt5.last_error()}"
        return True, "closed"
    return False, "position not found"


def save_trade(trade):
    try:
        config.ensure_data_dir()
        file_exists = os.path.exists(config.TRADES_FILE)
        import csv
        with open(config.TRADES_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["ts_open", "symbol", "side", "lots", "entry", "sl", "tp", "order", "deal"])
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                trade.get("symbol"),
                trade.get("side"),
                trade.get("volume") or trade.get("lots"),
                trade.get("price"),
                trade.get("sl"),
                trade.get("tp"),
                trade.get("order"),
                trade.get("deal"),
            ])
    except Exception:
        pass
