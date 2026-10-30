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
from multi_bot.executor import initialize, shutdown, open_position, save_trade, check_order
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
            f"lots={opp['lots']} risk=${opp.get('risk_usd')} src={opp.get('source')}")
    return opportunities


def run_execute(opportunities):
    if not opportunities:
        log("no opportunities — nothing to execute")
        return []
    ok, why = execution_gate()
    if not ok:
        log(f"execution blocked: {why}")
    if ok and not mconfig.DRY_RUN:
        return _execute_real(opportunities)
    if mconfig.DRY_RUN:
        _dry_run(opportunities, blocked_reason="" if ok else why)
    return []


def _execute_real(opportunities):
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


def _dry_run(opportunities, blocked_reason=""):
    """
    فحص جاف: نفس الطلب يمرّ على مدقق الوسيط `order_check` ثم يتوقف.
    لا يوجد `order_send` في هذا المسار — لذلك لا يمكن أن يفتح صفقة ولو أُخطئ.
    """
    log("dry-run: checking orders against broker validator (nothing is sent)")
    records = []
    for opp in opportunities:
        verdict, detail = check_order(opp["symbol"], opp["side"], opp["lots"],
                                      opp["sl"], opp["tp"])
        detail.update({"side": opp["side"], "score": opp.get("score"),
                       "verdict": verdict, "blocked_by": blocked_reason})
        records.append(detail)
        log(f"  DRY-RUN {opp['symbol']} {opp['side']} lots={opp['lots']} "
            f"price={detail.get('price')} sl={detail.get('sl')} tp={detail.get('tp')} "
            f"-> {verdict} retcode={detail.get('retcode')} {detail.get('comment', '')} "
            f"margin={detail.get('margin')} free={detail.get('margin_free')}")
    try:
        mconfig.ensure_data_dir()
        with open(mconfig.DRY_RUN_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": utcnow_iso(), "count": len(records), "checks": records},
                      f, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"dry-run save skipped: {type(exc).__name__}")
    return records


def main():
    log(f"started at {utcnow_iso()}")
    ok, msg = initialize()
    if not ok:
        log(f"FATAL: MT5 unavailable — {msg}")
        print("::error::MT5 unavailable in cloud — aborting run", flush=True)
        shutdown()
        sys.exit(2)
    log("MT5 connected | "
        f"equity={guard.equity():.2f} positions={len(guard.live_positions())}")
    synced, detail = guard.warmup_history()
    log(f"history warmup: synced={synced} {detail}")
    # 2026-10-29: بعد التسخين فقط تُصدَّق الأرقام (السجل كان فارغاً كذباً في الثانية الأولى)
    log("broker truth | "
        f"opened_today={guard.trades_opened_today()} "
        f"deals_today={guard.day_deal_stats()} "
        f"equity={guard.equity():.2f} positions={len(guard.live_positions())}")
    risk_now = guard.open_risk_usd()
    budget = mconfig.MAX_TOTAL_RISK_PCT * max(guard.equity(), 0.0)
    log(f"risk budget | open=${risk_now} of ${budget:.2f} "
        f"({mconfig.MAX_TOTAL_RISK_PCT*100:.0f}% of equity) "
        f"trades_per_day={'unlimited' if mconfig.MAX_TRADES_PER_DAY <= 0 else mconfig.MAX_TRADES_PER_DAY}")

    opportunities = run_scan()
    executed = run_execute(opportunities)

    blocked, why, detail = guard.kill_switch()
    log(f"safety: {'blocked' if blocked else 'clear'} {why} {detail}")
    log(f"finished: scanned={len(opportunities)}, executed={len(executed)}")
    shutdown()


if __name__ == "__main__":
    main()
