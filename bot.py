import time
import logging
import sys

import MetaTrader5 as mt5
import pandas as pd

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("MT5Bot")

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def ema_series(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def compute_signal(symbol: str, tf: int) -> tuple:
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, config.BARS_FOR_MA)
    if rates is None or len(rates) < config.SLOW_MA + 2:
        raise RuntimeError(f"no rates for {symbol}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    close = pd.Series(df["close"].astype(float))
    close_closed = close.iloc[:-1]

    fast = ema_series(close_closed, config.FAST_MA)
    slow = ema_series(close_closed, config.SLOW_MA)

    prev_fast, prev_slow = fast.iloc[-2], slow.iloc[-2]
    cur_fast, cur_slow = fast.iloc[-1], slow.iloc[-1]

    if cur_fast > cur_slow and prev_fast <= prev_slow:
        return "BUY", cur_fast
    if cur_fast < cur_slow and prev_fast >= prev_slow:
        return "SELL", cur_fast
    return None, cur_fast


def pip_size(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    point = info.point
    return point * 10 if info.digits >= 4 else point


def lot_for_risk(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    balance = mt5.account_info().equity
    loss_per_lot = config.SL_PIPS * pip_size(symbol) * info.trade_tick_value * info.trade_contract_size
    if loss_per_lot <= 0:
        return config.LOT_SIZE
    lots = (balance * config.RISK_PERCENT / 100.0) / loss_per_lot
    lots = max(info.volume_min, min(lots, info.volume_max))
    if info.volume_step:
        lots = round(lots / info.volume_step) * info.volume_step
    return round(lots, 2)


def spread_ok(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    return info.spread <= config.MAX_SPREAD_POINTS


def close_positions(symbol: str, reason: str):
    positions = mt5.positions_get(symbol=symbol, magic=config.MAGIC)
    if not positions:
        return
    for pos in positions:
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": config.MAGIC,
            "comment": f"close {reason}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log.info(f"closed position {pos.ticket} ({reason})")
        else:
            log.error(f"close failed ticket={pos.ticket}: {result} {mt5.last_error()}")


def open_trade(symbol: str, direction: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        log.error(f"no symbol info: {symbol}")
        return
    if not info.visible:
        mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    volume = lot_for_risk(symbol) if config.ACCOUNT_PERCENT_RISK else config.LOT_SIZE

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    entry = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    sl = tp = 0.0
    if config.USE_SL:
        sl = entry - pip_size(symbol) * config.SL_PIPS if order_type == mt5.ORDER_TYPE_BUY else entry + pip_size(symbol) * config.SL_PIPS
    if config.USE_TP:
        tp = entry + pip_size(symbol) * config.TP_PIPS if order_type == mt5.ORDER_TYPE_BUY else entry - pip_size(symbol) * config.TP_PIPS

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": entry,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": config.MAGIC,
        "comment": f"EMA cross {direction}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"opened {direction} {volume} @ {entry} sl={sl} tp={tp}")
    else:
        log.error(f"order failed: {result} {mt5.last_error()}")


def main():
    live = mt5.initialize(
        config.MT5_PATH,
        login=config.MT5_LOGIN,
        password=config.MT5_PASSWORD,
        server=config.MT5_SERVER,
    )
    if not live:
        log.error(f"MT5 initialize failed: {mt5.last_error()}")
        return

    account = mt5.account_info()
    log.info(f"connected to {account.server} | login={account.login} | balance={account.balance:.2f} {account.currency}")

    symbol = config.SYMBOL
    tf = TIMEFRAMES.get(config.TIMEFRAME)
    if tf is None:
        log.error(f"bad timeframe: {config.TIMEFRAME}")
        return
    if not mt5.symbol_select(symbol, True):
        log.error(f"symbol_select failed for {symbol}")
        return

    last_log = 0
    while True:
        if not spread_ok(symbol):
            log.warning(f"spread too high on {symbol}, skipping")
            time.sleep(config.CHECK_INTERVAL)
            continue

        try:
            direction, _ = compute_signal(symbol, tf)
        except RuntimeError as exc:
            log.error(str(exc))
            time.sleep(config.CHECK_INTERVAL)
            continue

        positions = mt5.positions_get(symbol=symbol, magic=config.MAGIC) or []
        has_position = len(positions) > 0

        if direction and has_position and config.CLOSE_ON_REVERSE_SIGNAL:
            pos = positions[0]
            pos_dir = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
            if pos_dir != direction:
                close_positions(symbol, "reverse signal")

        positions = mt5.positions_get(symbol=symbol, magic=config.MAGIC) or []
        if not positions and direction and config.ALLOW_NEW_POSITION:
            open_trade(symbol, direction)

        if time.time() - last_log >= 60:
            log.info(f"checking {symbol} {config.TIMEFRAME} EMA({config.FAST_MA}/{config.SLOW_MA}) | signal={direction} | open_positions={len(positions)}")
            last_log = time.time()

        time.sleep(config.CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("stopped by user")
    finally:
        mt5.shutdown()