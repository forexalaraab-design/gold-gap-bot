#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main_multi.py — نقطة بداية بوت التحليل اليومي متعدد الأزواج
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

from multi_bot import config as _cfg
from multi_bot import config as mconfig
from multi_bot.calendar import fetch_events, get_events_for_symbol, has_high_impact_near
from multi_bot.sentiment import get_symbol_sentiment
from multi_bot.analyst import analyst_consensus
from multi_bot.scanner import scan_all_symbols, save_opportunities
from multi_bot.executor import initialize, shutdown, open_position, save_trade
from multi_bot.scheduler import can_trade_today, record_trade


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[multi] {msg}", flush=True)


def run_scan():
    log("scan start")
    try:
        fetch_events(force_refresh=True)
    except Exception:
        pass
    opportunities = scan_all_symbols()
    save_opportunities(opportunities)
    log(f"scan done: {len(opportunities)} opportunities")
    for opp in opportunities:
        log(f"  {opp['symbol']} {opp['side']} score={opp['score']:.2f} entry={opp['entry']} sl={opp['sl']} tp={opp['tp']} lots={opp['lots']}")
    return opportunities


def run_execute(opportunities):
    if not opportunities:
        return []
    if not can_trade_today():
        log("daily limit reached, skip execution")
        return []
    ok, msg = initialize()
    if not ok:
        log(f"MT5 init failed: {msg}")
        return []
    executed = []
    for opp in opportunities:
        symbol = opp["symbol"]
        side = opp["side"]
        lots = opp["lots"]
        sl = opp["sl"]
        tp = opp["tp"]
        if lots < 0.01:
            continue
        trade, msg = open_position(symbol, side, lots, sl, tp)
        if trade:
            log(f"OPENED {symbol} {side} lots={lots} entry={trade['price']} sl={sl} tp={tp}")
            save_trade(trade)
            record_trade(trade, pnl=0.0)
            executed.append(trade)
        else:
            log(f"OPEN FAILED {symbol} {side}: {msg}")
    shutdown()
    return executed


def main():
    log(f"started at {utcnow_iso()}")
    opportunities = run_scan()
    executed = run_execute(opportunities)
    log(f"finished: scanned={len(opportunities)}, executed={len(executed)}")


if __name__ == "__main__":
    main()
