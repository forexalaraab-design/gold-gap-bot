#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live.py — حلقة مراقبة فجوة مستمرة بإغلاق متعدد الطبقات

تغييرات رئيسية:
  1. إغلاق نشط داخل الحلقة الرئيسية (كل ~3 ثوانٍ) — لا تعتمد فقط على run_trade_cycle
  2. دائرة أمان Daily Loss و Consecutive Losses
  3. متابعة الإنجاز: آخر تشغيل، آخر صفقة، آخر إغلاق
  4. reconcile دوري لمنع cache stale
  5. مراقبة الصفقة المفتوحة من BIAS (عبر وضع global/mid وتتبع PnL)
"""

import os
import time
import json
from datetime import datetime, timezone

import config
import gold_price
import main
import cbot
from cbot import CtraderSession
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, DeferredLock
from twisted.internet.task import deferLater
from twisted.internet.threads import deferToThread


def utcnow_iso():
    return main.utcnow_iso()


def _ts(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%H:%M:%S")


# قفل جزئي لإغلاق/فتح الصفقات (لمنع race)
_trade_lock = DeferredLock()


@inlineCallbacks
def live_loop():
    token = main.resolve_token()
    state = main.load_state()
    rows = main.load_history()

    print(
        f"live: {config.DURATION_MIN} min, "
        f"poll {config.GLOBAL_POLL_SEC}s, mode={config.MODE}"
    )

    sess = CtraderSession()
    result = {"ts": utcnow_iso()}
    closed_this_run = []
    opened_this_run = []

    try:
        # ---- الاتصال (مع إعادة محاولة) ----
        for attempt in (1, 2, 3, 4):
            try:
                yield sess.connect()
                break
            except Exception:
                if attempt == 4:
                    raise
                yield deferLater(reactor, 5, lambda: None)

        # ---- المصادقة (مع تحديث توكن تلقائي) ----
        account = None
        auth_err = None
        for attempt in (1, 2, 3, 4):
            t = token
            if attempt > 1:
                t = main.refresh_token()
                if not t:
                    break
                try:
                    yield sess.connect()
                except Exception as exc:
                    print(f"reconnect before auth {attempt} failed: {exc!r}")
            try:
                account = yield sess.authenticate(t)
                auth_err = None
                if os.environ.get("CBOT_TOKEN_SYNC") == "1":
                    try:
                        rf = config.CBOT_REFRESH_TOKEN
                        if not rf and os.path.exists(config.TOKEN_FILE):
                            rf = json.load(
                                open(config.TOKEN_FILE, encoding="utf-8")
                            ).get("refreshToken", "")
                        main.sync_tokens(t, rf)
                    except Exception as exc:
                        print("early token sync failed:", exc)
                break
            except Exception as exc:
                auth_err = exc
                print(f"auth attempt {attempt} failed: {exc!r}")
                yield deferLater(reactor, 5, lambda: None)
        if account is None:
            raise auth_err or RuntimeError("authentication failed")

        result["account_id"] = account
        trader = yield sess.get_trader()
        result["balance"] = trader.balance
        result["money_digits"] = trader.moneyDigits
        result["balance_usd"] = (
            trader.balance / (10 ** trader.moneyDigits)
            if trader.moneyDigits else trader.balance
        )

        # ---- رمز الذهب ----
        symbol_id = yield sess.find_symbol(config.SYMBOL)
        info = yield sess.symbol_info(symbol_id)
        volume = int(round(config.LOT * info["lotSize"]))
        result["symbol_id"] = symbol_id
        result["lot_size"] = info["lotSize"]
        result["volume"] = volume
        result["digits"] = info["digits"]

        sess.subscribe_persistent(symbol_id)
        print(f"live: subscribed symbol={symbol_id}, volume={volume}")

        # ---- FORCE_TEST_OPEN (اختبار توابع على الديمو) ----
        if config.FORCE_TEST_OPEN and config.ENVIRONMENT.strip().lower() == "demo":
            try:
                existing = yield sess.open_positions(symbol_id)
                if existing:
                    print(
                        f"FORCE-TEST SKIP (already open): "
                        f'{[(p.positionId, float(p.price)) for p in existing]}'
                    )
                else:
                    res = yield sess.open_market(
                        symbol_id, "BUY", volume,
                        label="FORCE-TEST", comment="",
                    )
                    print(
                        f"FORCE-TEST OPEN OK positionId={res.position.positionId}"
                    )
                    if res.position:
                        pid = res.position.positionId
                        entry0 = float(res.position.price)
                        for dist, scale in (
                            (5.0, config.SPOT_SCALE),
                            (5.0, 100.0),
                            (0.5, 100.0),
                            (20.0, 100.0),
                            (50.0, 100.0),
                        ):
                            try:
                                yield sess.set_sltp(
                                    pid,
                                    int(round((entry0 - dist) * scale)),
                                    int(round((entry0 + dist) * scale)),
                                )
                                print(
                                    f"FORCE-TEST SETSLTP OK dist={dist} scale={int(scale)}"
                                )
                                break
                            except Exception as exc:
                                print(
                                    f"FORCE-TEST SETSLTP FAIL dist={dist} scale={int(scale)}: {exc!r}"
                                )
                        try:
                            yield sess.close_position(pid)
                            print("FORCE-TEST CLOSE OK")
                        except Exception as exc:
                            print("FORCE-TEST CLOSE FAIL:", repr(exc))
            except Exception as exc:
                print("FORCE-TEST FAIL:", repr(exc))

        # ---- متابعة الحالة (للإغلاق المستمر) ----
        open_position_id = None
        open_position = None
        open_side = None
        open_entry_price = None
        open_st_pos = None  # نسخة من state["position"]
        peak = None

        # ---- حلقة المراقبة (كل ~3 ثوانٍ) ----
        end = time.time() + config.DURATION_MIN * 60
        last_save = time.time()
        last_append = 0.0
        last_bal = time.time()
        last_gap = None
        last_reconcile = 0.0

        while time.time() < end:
            now = time.time()

            # ----- جلب السعر العالمي -----
            try:
                global_price, source, source_ts = yield deferToThread(
                    gold_price.get_global_gold_price
                )
            except Exception as exc:
                print(f"{_ts(now)}  global error: {exc!r}")
                yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                continue

            # ----- أحدث tick من المنصة -----
            spot = sess.latest_spot(symbol_id)
            if spot is None:
                yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                continue
            bid, ask, sp_ts = spot
            mid = (bid + ask) / 2 / config.SPOT_SCALE
            gap = mid - global_price

            # ----- إضافة إلى السجل -----
            changed = last_gap is None or abs(gap - last_gap) >= config.APPEND_TOLERANCE
            if now - last_append >= config.APPEND_EVERY_SEC or changed:
                rows.append({"ts": utcnow_iso(), "global": global_price,
                             "platform": mid, "gap": gap})
                last_append = now
                last_gap = gap
                if len(rows) > config.MAX_HISTORY_ROWS:
                    rows = rows[-config.MAX_HISTORY_ROWS:]

            # ----- الإحصاءات -----
            stats = main.compute_stats(rows[:-1], verbose=False)

            # ----- تحديث الرصيد -----
            if now - last_bal >= 15:
                try:
                    trader = yield sess.get_trader()
                    result["balance"] = trader.balance
                    result["money_digits"] = trader.moneyDigits
                    result["balance_usd"] = (
                        trader.balance / (10 ** trader.moneyDigits)
                        if trader.moneyDigits else trader.balance
                    )
                    last_bal = now
                except Exception:
                    pass

            # ----- المراقبة: إغلاق نشط -----
            should_close = False
            close_reason = None
            close_pnl = 0.0
            position_id_to_close = None
            volume_to_close = None

            # المتابعة النظامية: كل 30 ثانية نراجع الصفقات المفتوحة
            if now - last_reconcile >= 30:
                positions = None
                try:
                    positions = yield sess.open_positions(symbol_id, max_age=0.0)
                    last_reconcile = now
                except Exception as exc:
                    print(f"reconcile warn: {exc!r}")

                if positions:
                    pos = positions[0]
                    position_id_to_close = pos.positionId
                    volume_to_close = getattr(pos.tradeData, "volume", 100)
                    open_position = pos
                    open_entry_price = float(pos.price)
                    open_side = (
                        "SELL" if "SELL" in str(pos.tradeData.tradeSide).upper()
                        else "BUY"
                    )
                    open_st_pos = state.get("position")
                    if open_st_pos is None or not isinstance(open_st_pos, dict):
                        open_st_pos = {"pnl_peak_usd": 0.0, "pnl_track": []}
                        state["position"] = open_st_pos
                    peak = float(open_st_pos.get("pnl_peak_usd") or 0)
                else:
                    # لا توجد صفقة مفتوحة
                    if open_position_id is not None:
                        # كان يوجد صفقة ولم يعد — ربما أغلقت خارجياً
                        if state.get("position") is not None:
                            st_p = state.get("position", {})
                            ts_open = st_p.get("opened_at")
                            ts_close = utcnow_iso()
                            _record_external_close(state, ts_open, ts_close, gap,
                                                  st_p.get("entry_gap"),
                                                  st_p.get("entry_price"),
                                                  mid, config.MAX_ENTRY_GAP_USD,
                                                  result)
                            state["position"] = None
                            opened_position_id = None  # reset
                            print("detected external close — recorded")
                    open_position = None
                    open_position_id = None
                    open_entry_price = None
                    open_side = None
                    open_st_pos = None
                    peak = None

            # إذا كانت هناك صفقة مفتوحة، فحص الإغلاق
            if open_position_id is not None and open_position is not None:
                # حساب PnL الحالي
                digits = result["digits"] or 2
                net_pnl, gross_pnl, fees = main.dynamic_pnl_usd(
                    open_position, mid, digits,
                    result["money_digits"] or 2,
                )
                if open_st_pos is not None:
                    st_peak = float(open_st_pos.get("pnl_peak_usd") or 0)
                    peak = max(st_peak, net_pnl)
                    open_st_pos["pnl_peak_usd"] = round(peak, 2)
                    open_st_pos["pnl_last_usd"] = round(net_pnl, 2)
                    track = open_st_pos.setdefault("pnl_track", [])
                    track.append(round(net_pnl, 2))
                    if len(track) > 120:
                        del track[:-120]

                # فحص الطبقات الخمس للإغلاق
                closing_mgr = main.ClosingManager(state, config)
                closing_mgr.init_from_state(state)
                should_close, close_reason = closing_mgr.check_close(
                    open_position, mid, global_price, stats,
                    open_st_pos, now, result["money_digits"] or 2,
                )

                if should_close:
                    # الإغلاق النشط
                    try:
                        yield _trade_lock.acquire()
                        try:
                            yield sess.close_position(
                                open_position_id,
                                volume=volume_to_close,
                                max_retries=3,
                            )
                            print(
                                f"✓ LIVE-CLOSE: reason={close_reason}, "
                                f"pnl={net_pnl:.2f}, peak={peak:.2f}"
                            )
                            closed_this_run.append(close_reason)
                            # تحديث الأداء
                            if net_pnl > 0:
                                closing_mgr.record_win()
                            else:
                                closing_mgr.record_loss()
                            closing_mgr.save_perf_to_state(state)

                            # تسجيل الإغلاق في trades.csv
                            # نسخ البيانات من st_pos
                            st_p = state.get("position", {})
                            main._record_close(state, {
                                "ts_open": st_p.get("opened_at"),
                                "ts_close": utcnow_iso(),
                                "side": open_side,
                                "entry_gap": st_p.get("entry_gap"),
                                "close_gap": gap,
                                "entry_price": st_p.get("entry_price"),
                                "close_price": mid,
                                "pnl_units": None,  # يتم حسابه لاحقاً
                                "pnl_usd": round(net_pnl, 2),
                                "fees_usd": round(fees, 2),
                                "pnl_net_usd": round(net_pnl, 2),
                                "reason": close_reason,
                                "pnl_peak_usd": round(peak, 2),
                            })
                        finally:
                            yield _trade_lock.release()
                    except Exception as exc:
                        print(f"live-close failed ({close_reason}): {exc!r}")

                    # مسح الحالة بعد الإغلاق
                    open_position_id = None
                    open_position = None
                    open_entry_price = None
                    open_side = None
                    open_st_pos = None
                    peak = None
                    state["position"] = None
                    state["cooldown_until"] = now + config.COOLDOWN_MINUTES * 60

            # ----- الفتح (إذا لم تكن هناك صفقة) -----
            if open_position_id is None and config.MODE == "trade":
                scale = (
                    stats.get("mad") if config.USE_MAD and stats.get("mad") else 0
                ) or stats["sd"] if stats else 0
                centre = (
                    stats["median"] if config.USE_MAD and stats.get("mad") else stats["mean"]
                ) if stats else 0
                if scale > 0 and stats:
                    z = (gap - centre) / scale
                else:
                    z = 0.0

                result["z"] = z

                # فحص ما إذا كان يمكن التداول اليوم
                can_trade_today = True
                perf = state.get("perf", {})
                daily_pnl = perf.get("running_daily_pnl", 0.0)
                consecutive_losses = perf.get("consecutive_losses", 0)
                trades_today = perf.get("trades_today", 0)
                if daily_pnl <= -config.MAX_DAILY_LOSS_USD:
                    can_trade_today = False
                    print("circuit breaker: daily loss exceeded")
                if consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                    can_trade_today = False
                    print("circuit breaker: consecutive losses exceeded")
                if trades_today >= config.MAX_TRADES_PER_DAY:
                    can_trade_today = False
                    print("circuit breaker: max trades today reached")

                if abs(z) >= config.Z_ENTRY and can_trade_today:
                    cooldown_left = state.get("cooldown_until", 0) - now
                    in_session_now = main.in_session(
                        datetime.now(timezone.utc)
                    )
                    bal_usd = result.get("balance_usd", 0)

                    if (
                        bal_usd >= config.MIN_BALANCE_TO_TRADE
                        and cooldown_left <= 0
                        and in_session_now
                        and abs(gap) <= config.MAX_ENTRY_GAP_USD
                    ):
                        new_side = "SELL" if gap > 0 else "BUY"
                        # لا توجد صفقة — نفتح
                        try:
                            yield _trade_lock.acquire()
                            try:
                                trad_pre = yield sess.get_trader()
                                res = yield sess.open_market(
                                    symbol_id, new_side, volume,
                                    sl=None, tp=None,
                                    label="GAPBOT", comment="",
                                )
                                if res.position:
                                    pid = res.position.positionId
                                    entry0 = float(res.position.price)
                                    new_st_pos = {
                                        "positionId": pid,
                                        "side": new_side,
                                        "entry_gap": gap,
                                        "entry_price": entry0,
                                        "opened_at": utcnow_iso(),
                                        "pnl_peak_usd": 0.0,
                                        "pnl_track": [],
                                    }
                                    state["position"] = new_st_pos
                                    state["entry_balance_units"] = (
                                        trad_pre.balance
                                        if trad_pre is not None else 0
                                    )
                                    open_position_id = pid
                                    open_position = res.position
                                    open_entry_price = entry0
                                    open_side = new_side
                                    open_st_pos = new_st_pos
                                    peak = 0.0
                                    opened_this_run.append(new_side)
                                    print(
                                        f">>> OPEN: side={new_side}, "
                                        f"gap={gap:.2f}, z={z:.2f}, "
                                        f"price={entry0:.2f}"
                                    )
                                    # تحديث مؤشرات الأداء
                                    perf2 = state.get("perf", {})
                                    perf2["trades_today"] = perf2.get("trades_today", 0) + 1
                                    state["perf"] = perf2
                                    closing_mgr2 = main.ClosingManager(state, config)
                                    closing_mgr2.init_from_state(state)
                                    closing_mgr2.save_perf_to_state(state)
                            finally:
                                yield _trade_lock.release()
                        except Exception as exc:
                            print(f"open FAIL: {exc!r}")

            # ----- الحفظ الدوري -----
            if now - last_save >= 30:
                main.save_history(rows)
                state["stats"] = stats
                state["last_run"] = utcnow_iso()
                if open_position_id is not None:
                    st_p = state.get("position")
                    if st_p is None or not isinstance(st_p, dict):
                        state["position"] = {
                            "positionId": open_position_id,
                            "side": open_side,
                            "entry_gap": gap,
                            "entry_price": open_entry_price,
                            "opened_at": utcnow_iso(),
                            "pnl_peak_usd": peak or 0.0,
                            "pnl_track": [],
                        }
                main.save_state(state)
                last_save = now

            # ----- السجل -----
            z_str = f"{z:.2f}" if stats and abs(z) >= config.Z_ENTRY else "-"
            action_str = "no-op"
            if open_position_id is not None:
                action_str = f"hold:pnl={net_pnl:.2f}"
                if should_close:
                    action_str = f"live-close:{close_reason}"
            elif state.get("position") is not None:
                action_str = "open"
            print(
                f"{_ts(now)}  mid={mid:.2f} global={global_price:.2f} "
                f"gap={gap:.2f} z={z_str} action={action_str}"
            )

            yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)

        # ---- نهاية الدورة ----
        if open_position_id is not None:
            st_p = state.get("position", {})
            main._record_external_close(
                state,
                st_p.get("opened_at"),
                utcnow_iso(),
                gap,
                st_p.get("entry_gap"),
                st_p.get("entry_price"),
                mid,
                config.MAX_ENTRY_GAP_USD,
                result,
            )
            state["position"] = None

    except Exception:
        import traceback
        result["error"] = traceback.format_exc(limit=25)
    finally:
        main.save_history(rows)
        state["last_run"] = utcnow_iso()
        main.save_state(state)
        sess.stop()
        main._print_report(result, state)
        reactor.stop()


def _record_external_close(state, ts_open, ts_close, gap,
                            entry_gap, entry_price, close_price, max_gap,
                            result):
    """تسجيل إغلاق خارجي (فيuncesمن المستخدم أو السيرفر)."""
    if ts_open:
        net_gap = close_price - (entry_price or close_price)
        pnl_usd_guess = net_gap * config.LOT * 10  # تقريب خشن
        main._record_close(state, {
            "ts_open": ts_open,
            "ts_close": ts_close,
            "side": state.get("position", {}).get("side"),
            "entry_gap": entry_gap,
            "close_gap": gap,
            "entry_price": entry_price,
            "close_price": close_price,
            "pnl_units": None,
            "pnl_usd": round(pnl_usd_guess, 2),
            "reason": "external_close",
        })
    result["action"] = "external_close"


if __name__ == "__main__":
    d = live_loop()
    d.addErrback(lambda f: print("FATAL", f.getTraceback()))
    reactor.run()
