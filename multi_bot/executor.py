# -*- coding: utf-8 -*-
"""
multi_bot/executor.py — تنفيذ الصفقات عبر MT5
"""
import os
import time
import json
from datetime import datetime, timezone

from multi_bot import config


def _mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except Exception:
        return None


def initialize():
    mt5 = _mt5()
    if mt5 is None:
        return False, "MetaTrader5 not installed"
    path = getattr(config, "MT5_PATH", "") or os.environ.get("MT5_TERMINAL_PATH", "")
    if not path or not os.path.exists(path):
        return False, f"MT5 path not found: {path}"
    ok = mt5.initialize(path, login=config.MT5_LOGIN, password=config.MT5_PASSWORD, server=config.MT5_SERVER)
    if not ok:
        return False, f"MT5 init failed: {mt5.last_error()}"
    return True, "connected"


def shutdown():
    mt5 = _mt5()
    if mt5:
        try:
            mt5.shutdown()
        except Exception:
            pass


def open_position(symbol, side, lots, sl, tp):
    mt5 = _mt5()
    if mt5 is None:
        return None, "no mt5"
    sym = (config.MT5_SYMBOL_SUFFIX + symbol).upper()

    # Prevent multiple positions on the same symbol
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            if pos.symbol.upper() == sym:
                return None, f"already_open:{sym}"

    try:
        mt5.symbol_select(sym, True)
    except Exception:
        pass
    info = mt5.symbol_info(sym)
    if info is None:
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
        info = mt5.symbol_info(sym)
    if info is None:
        return None, f"symbol not found: {sym}"
    if hasattr(info, "visible") and not info.visible:
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return None, f"tick not found: {sym}"
    price = tick.ask if side == "BUY" else tick.bid

    # Validate SL/TP direction before sending
    if side == "BUY":
        if float(sl) >= price:
            sl, tp = tp, sl  # swap if SL is above entry for BUY
    elif side == "SELL":
        if float(sl) <= price:
            sl, tp = tp, sl  # swap if SL is below entry for SELL

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
