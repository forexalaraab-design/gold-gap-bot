import json
import os
import sys
import time
from datetime import datetime, timezone

import config
import gold_price
from cbot import CtraderSession
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, DeferredLock
from twisted.internet.task import deferLater
from twisted.internet.threads import deferToThread
import main as _main


# =============================================================================
# مساعدة
# =============================================================================

def utcnow_iso():
    return _main.utcnow_iso()


def _ts(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%H:%M:%S")


def _fmt(v):
    return _main._fmt(v)


def _record_close(state, rec):
    _main._record_close(state, rec)


def _record_external_close(state, ts_open, ts_close, gap,
                           entry_gap, entry_price, close_price, max_gap,
                           result):
    _main._record_external_close(state, ts_open, ts_close, gap,
                                 entry_gap, entry_price, close_price,
                                 max_gap, result)


# =============================================================================
# قفل تجاري (لحماية الفتح/الإغلاق من التداخل)
# =============================================================================

_trade_lock = DeferredLock()


def _now_unix():
    return time.time()


# =============================================================================
# الحلقة الرئيسية (تعمل 3-5 دقائق ثم تتوقف عند انتهاء المهلة)
# =============================================================================

@inlineCallbacks
def live_loop():
    print(f"live: starting — duration={config.DURATION_MIN}min, "
          f"poll={config.GLOBAL_POLL_SEC}s, mode={config.MODE}",
          flush=True)

    token = _main.resolve_token()
    state = _main.load_state()
    rows = _main.load_history()

    sess = CtraderSession()
    result = {"ts": utcnow_iso()}
    last_reconcile = 0.0
    last_save = _now_unix()
    last_append = 0.0
    last_gap = None
    last_balance = 0.0
    peak = 0.0

    try:
        # --- الاتصال (إعادة محاولة 4 مرات) ---
        host = None
        for attempt in (1, 2, 3, 4):
            try:
                host = yield sess.connect()
                break
            except Exception as exc:
                if attempt == 4:
                    raise
                print(f"connect attempt {attempt} failed: {exc!r}, "
                      f"retry in 5s", flush=True)
                yield deferLater(reactor, 5, lambda: None)
        print(f"connected to {host}", flush=True)

        # --- المصادقة ---
        account = None
        for attempt in (1, 2, 3, 4):
            t = token
            if attempt > 1:
                t = _main.refresh_token()
                if not t:
                    break
                try:
                    yield sess.connect()
                except Exception as exc:
                    print(f"reconnect before auth {attempt}: {exc!r}",
                          flush=True)
            try:
                account = yield sess.authenticate(t)
                break
            except Exception as exc:
                print(f"auth attempt {attempt} failed: {exc!r}",
                      flush=True)
                yield deferLater(reactor, 5, lambda: None)
        if account is None:
            raise RuntimeError("authentication failed after all attempts")
        print(f"authenticated as account {account}", flush=True)

        # --- رمز الذهب ---
        symbol_id = yield sess.find_symbol(config.SYMBOL)
        info = yield sess.symbol_info(symbol_id)
        volume = int(round(config.LOT * info["lotSize"]))
        digits = info["digits"]
        result["symbol_id"] = symbol_id
        result["lot_size"] = info["lotSize"]
        result["volume"] = volume
        result["digits"] = digits
        result["balance"] = 0
        result["money_digits"] = digits
        print(f"symbol={config.SYMBOL} id={symbol_id} "
              f"volume={volume} digits={digits} lotSize={info['lotSize']}",
              flush=True)

        sess.subscribe_persistent(symbol_id)
        print(f"subscribed symbol={symbol_id}", flush=True)

        # --- FORCE_TEST_OPEN (ديمو فقط) ---
        if (config.FORCE_TEST_OPEN and
                config.ENVIRONMENT.strip().lower() == "demo"):
            try:
                existing = yield sess.open_positions(symbol_id)
                if existing:
                    print(f"FORCE-TEST SKIP (already open): "
                          f"{[p.positionId for p in existing]}", flush=True)
                else:
                    res = yield sess.open_market(
                        symbol_id, "BUY", volume,
                        label="FORCE-TEST", comment=""
                    )
                    print(f"FORCE-TEST OPEN OK positionId="
                          f"{res.position.positionId}", flush=True)
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
                                print(f"FORCE-TEST SETSLTP OK "
                                      f"dist={dist} scale={int(scale)}",
                                      flush=True)
                                break
                            except Exception as exc:
                                print(f"FORCE-TEST SETSLTP FAIL "
                                      f"dist={dist} scale={int(scale)}: "
                                      f"{exc!r}", flush=True)
                        yield sess.close_position(pid)
                        print("FORCE-TEST CLOSE OK", flush=True)
            except Exception as exc:
                print(f"FORCE-TEST FAIL: {exc!r}", flush=True)

        # --- المراقبة المستمرة ---
        end = _now_unix() + config.DURATION_MIN * 60
        while _now_unix() < end:
            now = _now_unix()
            tick_start = now

            # ----- جلب سعر الذهب العالمي -----
            global_price = 0.0
            source = "none"
            source_ts = ""
            try:
                gp = yield deferToThread(gold_price.get_global_gold_price)
                global_price, source, source_ts = gp
            except Exception as exc:
                print(f"{_ts(now)} global error: {exc!r}", flush=True)
                yield deferLater(reactor, config.GLOBAL_POLL_SEC,
                                lambda: None)
                continue

            # ----- آخر سعر من المنصة -----
            spot = sess.latest_spot(symbol_id)
            if spot is None:
                yield deferLater(reactor, config.GLOBAL_POLL_SEC,
                                lambda: None)
                continue
            bid, ask, sp_ts = spot
            mid = (bid + ask) / 2 / config.SPOT_SCALE
            gap = mid - global_price

            # ----- حفظ السجل -----
            changed = (last_gap is None or
                       abs(gap - last_gap) >= config.APPEND_TOLERANCE)
            if (now - last_append >= config.APPEND_EVERY_SEC or
                    changed):
                rows.append({
                    "ts": utcnow_iso(),
                    "global": global_price,
                    "platform": mid,
                    "gap": gap,
                })
                last_append = now
                last_gap = gap
                if len(rows) > config.MAX_HISTORY_ROWS:
                    rows = rows[-config.MAX_HISTORY_ROWS:]

            # ----- إحصائيات الفجوة -----
            stats = _main.compute_stats(rows[:-1], verbose=False)

            # ----- رصيد السوق كل 15 ثانية -----
            if now - last_balance >= 15:
                try:
                    trader = yield sess.get_trader()
                    bal = trader.balance
                    md = trader.moneyDigits
                    result["balance"] = bal
                    result["money_digits"] = md
                    last_balance = bal / (10 ** md) if md else bal
                except Exception:
                    pass

            # ----- فحص الصفقة المفتوحة كل 30 ثانية -----
            reconcile_now = (now - last_reconcile >= 30)
            st_pos = state.get("position")
            pos_id = None
            pos_vol = None
            pos = None
            open_side = None
            open_entry = None
            stored_peak = 0.0

            if reconcile_now:
                last_reconcile = now
                positions = None
                try:
                    positions = yield sess.open_positions(
                        symbol_id, max_age=0.0)
                except Exception as exc:
                    print(f"reconcile warn: {exc!r}", flush=True)
                if positions:
                    p = positions[0]
                    pos_id = p.positionId
                    pos_vol = getattr(p.tradeData, "volume", 100)
                    pos = p
                    raw_price = float(p.price) if p.price else None
                    if raw_price is not None and raw_price > 10000:
                        raw_price = raw_price / config.SPOT_SCALE
                    open_entry = raw_price
                    open_side = ("SELL" if
                                 "SELL" in str(p.tradeData.tradeSide).upper()
                                 else "BUY")
                    stored = state.get("position") or {}
                    if isinstance(stored, dict):
                        open_entry = (stored.get("entry_price") or
                                      open_entry)
                        stored_peak = float(stored.get("pnl_peak_usd") or 0)
                        peak = max(stored_peak, peak)
                        st_pos = stored
                else:
                    if state.get("position") is not None:
                        st_p = state.get("position", {})
                        ts_open = st_p.get("opened_at")
                        ts_close = utcnow_iso()
                        _record_external_close(
                            state, ts_open, ts_close, gap,
                            st_p.get("entry_gap"),
                            st_p.get("entry_price"),
                            mid, config.MAX_ENTRY_GAP_USD,
                            result)
                        print("detected external close — recorded",
                              flush=True)
                        st_pos = None

            # ----- فحص الإغلاق -----
            should_close = False
            close_reason = None
            pnl_net = 0.0
            if pos_id is not None and st_pos is not None:
                digits = result.get("digits") or 2
                md = result.get("money_digits") or 2
                net_pnl, gross_pnl, fees = _main.dynamic_pnl_usd(
                    pos, mid, digits, md)
                if st_pos.get("pnl_peak_usd") is not None:
                    peak = max(float(st_pos["pnl_peak_usd"]), net_pnl)
                    st_pos["pnl_peak_usd"] = round(peak, 2)
                st_pos["pnl_last_usd"] = round(net_pnl, 2)
                pnl_net = net_pnl

                closing_mgr = _main.ClosingManager(state, config)
                closing_mgr.init_from_state(state)
                should_close, close_reason = closing_mgr.check_close(
                    pos, mid, global_price, stats,
                    st_pos, now, md)

                if should_close:
                    print(f"✓ closing: reason={close_reason}, "
                          f"pnl={pnl_net:.2f}, peak={peak:.2f}",
                          flush=True)
                    try:
                        yield _trade_lock.acquire()
                        try:
                            yield sess.close_position(
                                pos_id, volume=pos_vol,
                                max_retries=3)
                            print(f"LIVE-CLOSE OK: {close_reason} "
                                  f"pnl={pnl_net:.2f}", flush=True)
                            if net_pnl > 0:
                                closing_mgr.record_win()
                            else:
                                closing_mgr.record_loss()
                            closing_mgr.save_perf_to_state(state)
                            _record_close(state, {
                                "ts_open": st_pos.get("opened_at"),
                                "ts_close": utcnow_iso(),
                                "side": open_side,
                                "entry_gap": st_pos.get("entry_gap"),
                                "close_gap": gap,
                                "entry_price": open_entry,
                                "close_price": mid,
                                "pnl_units": round(net_pnl, 2),
                                "pnl_usd": round(net_pnl, 2),
                                "fees_usd": round(fees, 2),
                                "pnl_net_usd": round(net_pnl, 2),
                                "reason": close_reason,
                                "pnl_peak_usd": round(peak, 2),
                            })
                            result["action"] = "close:" + close_reason
                            result["close_pnl_usd"] = pnl_net
                        finally:
                            yield _trade_lock.release()
                    except Exception as exc:
                        print(f"live-close failed ({close_reason}): "
                              f"{exc!r}", flush=True)
                        result["close_failed"] = repr(exc)
                        result["action"] = "close_pending:" + close_reason
                    pos_id = None
                    st_pos = None
                    state["position"] = None
                    state["cooldown_until"] = (now +
                                                config.COOLDOWN_MINUTES * 60)

            # ----- تنفيذ دورة التداول (فتح + إغلاق) من main.py -----
            closing_mgr_local = _main.ClosingManager(state, config)
            closing_mgr_local.init_from_state(state)
            try:
                yield _main.run_trade_cycle(
                    sess, mid, global_price, stats,
                    state, result, closing_mgr_local)
            except Exception as exc:
                print(f"trade-cycle error: {exc!r}", flush=True)

            # ----- إحصائيات حية -----
            z_val = None
            if stats:
                sd = (stats.get("mad") if
                      config.USE_MAD and stats.get("mad") else 0) or \
                     stats["sd"]
                centre = (stats["median"] if
                          config.USE_MAD and stats.get("mad")
                          else stats["mean"])
                if sd > 0:
                    z_val = (gap - centre) / sd

            action_str = "none"
            if pos_id is not None:
                action_str = f"hold:pnl={pnl_net:.2f}"
                if should_close:
                    action_str = f"live-close:{close_reason}"
            elif state.get("position") is not None:
                action_str = "open"
            if z_val is not None and abs(z_val) >= config.Z_ENTRY:
                z_str = f"{z_val:.2f}"
            else:
                z_str = "-"

            print(f"{_ts(now)} mid={mid:.2f} global={global_price:.2f} "
                  f"gap={gap:.2f} z={z_str} action={action_str}",
                  flush=True)

            # ----- الحفظ الدوري كل 30 ثانية -----
            if now - last_save >= 30:
                _main.save_history(rows)
                state["stats"] = stats
                state["last_run"] = utcnow_iso()
                if pos_id is not None and st_pos is not None:
                    st_pos["positionId"] = pos_id
                    st_pos["side"] = open_side
                    st_pos["entry_gap"] = gap
                    st_pos["entry_price"] = open_entry
                    st_pos["opened_at"] = utcnow_iso()
                    st_pos["pnl_peak_usd"] = round(peak, 2)
                    st_pos["pnl_track"] = []
                    state["position"] = st_pos
                _main.save_state(state)
                last_save = now

            # ----- تأخير حتى الدورة التالية -----
            yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)

        # --- نهاية الدورة: إغلاق أي صفقة متبقية ---
        if state.get("position") is not None:
            st_p = state.get("position", {})
            if st_p.get("opened_at"):
                _record_external_close(
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
        result["error"] = traceback.format_exc(limit=30)
        print(f"FATAL in live_loop: {result['error']}", flush=True)
    finally:
        print("live: saving state & stopping...", flush=True)
        _main.save_history(rows)
        state["last_run"] = utcnow_iso()
        _main.save_state(state)
        sess.stop()
        try:
            _main._print_report(result, state)
        except Exception as exc:
            print(f"report error: {exc!r}", flush=True)
        reactor.stop()
        import sys as _sys
        _sys.exit(0)


# =============================================================================
# نقطة الدخول
# =============================================================================

if __name__ == "__main__":
    import signal

    def _sigterm(signum, frame):
        print("SIGTERM received — stopping", flush=True)
        try:
            reactor.stop()
        except Exception:
            pass
        import sys as _s
        _s.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    d = live_loop()
    d.addErrback(lambda f: print("FATAL", f.getTraceback(), flush=True))

    #_hard timeout: if the bot runs longer than DURATION_MIN + 60s, force stop
    _total_timeout = int((config.DURATION_MIN + 1.0) * 60)
    _hard_timer = reactor.callLater(_total_timeout, lambda: (
        print(f"hard timeout after {_total_timeout}s — stopping", flush=True),
        reactor.stop(),
        __import__("sys").exit(0)
    ))
    reactor.run()
