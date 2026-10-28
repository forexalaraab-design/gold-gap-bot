#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main_multi.py — نقطة بداية بوت التحليل اليومي متعدد الأزواج

2026-10-29 (جلسة الغرفة — إصلاح الهندسة):
  • MT5 يُهيَّأ **قبل** الفحص، والبيانات منه لا من Yahoo.
  • كل رفض يُكتب بسببه في data/scan_reasons.json.
  • لا تنفيذ إلا بعد: مفتاح تشغيل + بوابة 300$ + مفتاح إيقاف + تعرّض واحد.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

from multi_bot import config as mconfig
from multi_bot import guard
from multi_bot.calendar import fetch_events
from multi_bot.scanner import scan_all_symbols_detailed, save_opportunities, save_scan_reasons
from multi_bot.executor import initialize, shutdown, open_position, save_trade
from multi_bot.scheduler import execution_gate, record_trade


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[multi] {msg}", flush=True)


def run_scan():
    log("scan start")
    try:
        fetch_events(force_refresh=True)
    except Exception as exc:
        log(f"calendar fetch skipped: {type(exc).__name__}")
    opportunities, reasons = scan_all_symbols_detailed()
    save_opportunities(opportunities)
    save_scan_reasons(reasons)
    counts = {}
    for info in reasons.values():
        r = (info or {}).get("reason") or "passed"
        counts[r] = counts.get(r, 0) + 1
    log(f"scan done: {len(opportunities)} opportunities | rejects: {counts}")
    for opp in opportunities:
        log(f"  {opp['symbol']} {opp['side']} score={opp['score']:.2f} "
            f"entry={opp['entry']} sl={opp['sl']} tp={opp['tp']} "
            f"lots={opp['lots']} src={opp.get('source')}")
    return opportunities


def run_execute(opportunities):
    if not opportunities:
        log("no opportunities — nothing to execute")
        return []
    ok, why = execution_gate()
    if not ok:
        log(f"execution blocked: {why}")
        return []
    executed = []
    for opp in opportunities:
        symbol, side, lots = opp["symbol"], opp["side"], opp["lots"]
        if lots < 0.01:
            log(f"SKIP {symbol}: lots={lots} below minimum")
            continue
        trade, msg = open_position(symbol, side, lots, opp["sl"], opp["tp"])
        if trade:
            log(f"OPENED {symbol} {side} lots={lots} entry={trade['price']} "
                f"sl={opp['sl']} tp={opp['tp']}")
            save_trade(trade)
            record_trade(trade, pnl=0.0)
            executed.append(trade)
        else:
            log(f"OPEN FAILED {symbol} {side}: {msg}")
    return executed


def main():
    log(f"started at {utcnow_iso()}")
    ok, msg = initialize()
    if not ok:
        log(f"FATAL: MT5 unavailable — {msg}")
        print("::error::MT5 unavailable in cloud — aborting run", flush=True)
        shutdown()
        sys.exit(2)
    log("MT5 connected | "
        f"equity={guard.equity():.2f} positions={len(guard.live_positions())} "
        f"opened_today={guard.trades_opened_today()}")

    opportunities = run_scan()
    executed = run_execute(opportunities)

    blocked, why, detail = guard.kill_switch()
    log(f"safety: {'blocked' if blocked else 'clear'} {why} {detail}")
    log(f"finished: scanned={len(opportunities)}, executed={len(executed)}")
    shutdown()


if __name__ == "__main__":
    main()
