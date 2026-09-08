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


_trade_lock = DeferredLock()


def _now_unix():
    return time.time()


@inlineCallbacks
def live_loop():
    print(f"live: starting — duration={config.DURATION_MIN}min, "
          f"poll={config.GLOBAL_POLL_SEC}s, mode={config.MODE}",
          flush=True)

    token = _main.resolve_token()
    state = _main.load_state()
    rows = []

    sess = CtraderSession()
    result = {"ts": utcnow_iso()}
    last_reconcile = 0.0
    last_save = _now_unix()
    last_append = 0.0
    last_gap = None
    last_balance = 0.0
    peak = 0.0

    try:
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
                    print(f"reconnect before auth {attempt}: {exc!r}", flush=True)
            try:
                account = yield sess.authenticate(t)
                break
            except Exception as exc:
                print(f"auth attempt {attempt} failed: {exc!r}", flush=True)
                yield deferLater(reactor, 5, lambda: None)
        if account is None:
            raise RuntimeError("authentication failed after all attempts")
        print(f"authenticated as account {account}", flush=True)

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
              f"volume={volume} digits={digits} lotSize={info['lotSize']}", flush=True)

        sess.subscribe_persistent(symbol_id)
        print(f"subscribed symbol={symbol_id}", flush=True)

        # FORCE-TEST: اختبار يدوي فقط — يُعطّل تماماً أثناء التداول الحقيقي
        if (config.FORCE_TEST_OPEN
                and config.MODE != "trade"
                and config.ENVIRONMENT.strip().lower() == "demo"):
            try:
                existing = yield sess.open_positions(sess.account_id,
                                                     max_age=86400.0)
                if existing:
                    print(f"FORCE-TEST SKIP (already open): "
                          f"{[p.positionId for p in existing]}", flush=True)
                else:
                    res = yield sess.open_market(
                        symbol_id, "BUY", volume,
                        label="FORCE-TEST", comment=""
                    )
                    if isinstance(res, dict):
                        pos_id = res.get("positionId")
                        pos_price = None
                        pos_obj = res.get("position")
                        if pos_obj is not None:
                            entry0p = getattr(pos_obj, "price", None)
                            if entry0p is not None:
                                pos_price = float(entry0p)
                        if pos_price is None:
                            pos_price = mid
                        entry0 = pos_price
                    else:
                        pos_obj = getattr(res, "position", None)
                        pos_id = getattr(pos_obj, "positionId", None)
                        entry0p = getattr(pos_obj, "price", None)
                        entry0 = float(entry0p) if entry0p else mid
                    print(f"FORCE-TEST OPEN OK positionId={pos_id}", flush=True)
                    if pos_id:
                        for dist, scale in (
                            (5.0, config.SPOT_SCALE),
                            (5.0, 100.0),
                            (0.5, 100.0),
                            (20.0, 100.0),
                            (50.0, 100.0),
                        ):
                            try:
                                yield sess.set_sltp(
                                    pos_id,
                                    int(round((entry0 - dist) * scale)),
                                    int(round((entry0 + dist) * scale)),
                                )
                                print(f"FORCE-TEST SETSLTP OK "
                                      f"dist={dist} scale={int(scale)}", flush=True)
                                break
                            except Exception as exc:
                                print(f"FORCE-TEST SETSLTP FAIL "
                                      f"dist={dist} scale={int(scale)}: "
                                      f"{exc!r}", flush=True)
                        yield sess.close_position(pos_id)
                        print("FORCE-TEST CLOSE OK", flush=True)
            except Exception as exc:
                print(f"FORCE-TEST FAIL: {exc!r}", flush=True)

        # تنظيف الحساب من الصفقات العالقة القديمة (مرة واحدة فقط)
        # حتى يبدأ البوت بصفقة واحدة فقط كما هو مطلوب.
        if (config.MODE == "trade"
                and not state.get("cleanup_done_internal")):
            try:
                print("cleanup: closing stale open positions...", flush=True)
                nclosed = yield sess.close_all_positions(sess.account_id)
                # تحقق نهائي: هل اكتمل التنظيف؟
                if nclosed == 0:
                    state["cleanup_done_internal"] = True
                else:
                    remain = yield sess.open_positions(sess.account_id)
                    if not remain:
                        state["cleanup_done_internal"] = True
                        print("cleanup: all stale positions now closed",
                              flush=True)
                    else:
                        print(f"cleanup: {len(remain)} still open - will "
                              f"continue next run", flush=True)
            except Exception as exc:
                print(f"cleanup error: {exc!r}", flush=True)

        end = _now_unix() + config.DURATION_MIN * 60
        while _now_unix() < end:
            now = _now_unix()
            tick_start = now

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

            spot = sess.latest_spot(symbol_id)
            if spot is None:
                yield deferLater(reactor, config.GLOBAL_POLL_SEC,
                                lambda: None)
                continue
            bid, ask, sp_ts = spot
            # الحماية: أحياناً يصل bid=0 (قبل أول تحديث). لا نحسب mid
            # من (bid+ask)/2 مع bid=0 — كان ينتج أسعاراً منتصفة في سجل
            # الصفقات القديمة. نستخدم المتاح فقط.
            if not bid or not ask:
                if bid and not ask:
                    mid = bid / config.SPOT_SCALE
                elif ask and not bid:
                    mid = ask / config.SPOT_SCALE
                else:
                    print(f"  SKIP tick: bid={bid} ask={ask} both zero", flush=True)
                    yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                    continue
            else:
                mid = (bid + ask) / 2 / config.SPOT_SCALE
            # Sanity check: XAUUSD should be around 4000-5000
            if not (4000 <= mid <= 5000):
                print(f"  SKIP tick: mid={mid:.2f} out of range, bid={bid} ask={ask}", flush=True)
                yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                continue
            gap = mid - global_price

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

            stats = _main.compute_stats(rows[:-1], verbose=False)

            if now - last_balance >= 15:
                try:
                    trader = yield sess.get_trader()
                    bal = trader.balance
                    md = trader.moneyDigits
                    result["balance"] = bal
                    result["money_digits"] = md
                    bal_usd = bal / (10 ** md) if md else bal
                    result["balance_usd"] = bal_usd
                    last_balance = bal_usd
                except Exception:
                    pass

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
                        sess.account_id, max_age=86400.0)
                except Exception as exc:
                    print(f"reconcile warn: {exc!r}", flush=True)
                if positions:
                    p = positions[0]
                    pos_id = getattr(p, "positionId", None)
                    pos_vol = getattr(p.tradeData, "volume", 100)
                    pos = p
                    # ملاحظة: open_positions يعيد ProtoOAOrder وليس Position.
                    # لا نعتمد أبداً على سعر الـ order — نستخدم entry من الـ state.
                    raw_price = getattr(p, "price", None)
                    if raw_price is not None and raw_price > 10000:
                        raw_price = raw_price / config.SPOT_SCALE
                    stored = state.get("position") or {}
                    if isinstance(stored, dict):
                        open_entry = stored.get("entry_price") or raw_price
                        stored_peak = float(stored.get("pnl_peak_usd") or 0)
                        peak = max(stored_peak, peak)
                        st_pos = stored
                    else:
                        open_entry = raw_price
                    open_side = ("SELL" if
                                 "SELL" in str(p.tradeData.tradeSide).upper()
                                 else "BUY")
                else:
                    # اكتشاف الإغلاق الخارجي ممكن فقط عند توفر PositionList
                    # موثوق. في وضع state-only (مكتبة بدون PositionList) لا
                    # توجد قائمة حقيقية — إرجاع [] هنا ليس دليلاً على إغلاق،
                    # ولا يجوز مسح الصفقة من الحالة وإلا تفتح صفقة ثانية.
                    if (state.get("position") is not None
                            and getattr(sess, "_position_source", "")
                            == "position_list"):
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
                        # مسح الصفقة المفتوحة من الحالة — لا صفقة نشطة الآن
                        state["position"] = None
                        st_pos = None
                    else:
                        print(f"reconcile: no positions (source="
                              f"{getattr(sess, '_position_source', '?')}), "
                              f"state position kept, no external close",
                              flush=True)

            # ----- تنفيذ دورة التداول الكاملة (فتح + إغلاق) -----
            closing_mgr_full = _main.ClosingManager(state, config)
            closing_mgr_full.init_from_state(state)
            try:
                yield _main.run_trade_cycle(
                    sess, mid, global_price, stats,
                    state, result, closing_mgr_full)
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
                action_str = f"hold"
            elif state.get("position") is not None:
                # pos_id يُحدَّث كل reconcile (30s)؛ وجود position في الحالة
                # يعني أننا محتفظون بالصفقة — ليست فتحاً جديداً.
                action_str = "hold:state"
            if z_val is not None and abs(z_val) >= config.Z_ENTRY:
                z_str = f"{z_val:.2f}"
            else:
                z_str = "-"

            print(f"{_ts(now)} mid={mid:.2f} global={global_price:.2f} "
                  f"gap={gap:.2f} z={z_str} action={action_str}", flush=True)

            # ----- الحفظ الدوري كل 30 ثانية -----
            if now - last_save >= 30:
                _main.save_history(rows)
                state["stats"] = stats
                state["last_run"] = utcnow_iso()
                if pos_id is not None and st_pos is not None:
                    # تحديث الحقول فقط، بدون استبدال كامل لـ pnl_peak_usd
                    st_pos["positionId"] = pos_id
                    st_pos["side"] = open_side
                    st_pos["entry_gap"] = gap
                    st_pos["entry_price"] = open_entry
                    st_pos["opened_at"] = utcnow_iso()
                    # الاحتفاظ بـ pnl_peak_usd من الـ state الحالي إن وجد
                    if "pnl_peak_usd" not in st_pos or st_pos["pnl_peak_usd"] is None:
                        st_pos["pnl_peak_usd"] = 0.0
                    state["position"] = st_pos
                _main.save_state(state)
                last_save = now

            yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)

        # --- نهاية الدورة: نحافظ على الصفقة المفتوحة في الحالة؛
        #     لا نُغلقها زوراً (هذا كان يسبب تسجيل إغلاقات وهمية وفتح
        #     صفقات مكررة في كل دورة). الـ state سيُحفظ في finally أدناه. ---
        if state.get("position") is not None:
            print("live: exiting with position still open — keeping it in state",
                  flush=True)

    except Exception:
        import traceback
        result["error"] = traceback.format_exc(limit=30)
        print(f"FATAL in live_loop: {result['error']}", flush=True)
    finally:
        print("live: saving state & stopping...", flush=True)
        try:
            _main.save_history(rows)
        except Exception as exc:
            print(f"save_history error: {exc!r}", flush=True)
        state["last_run"] = utcnow_iso()
        try:
            _main.save_state(state)
        except Exception as exc:
            print(f"save_state error: {exc!r}", flush=True)
        try:
            sess.stop()
        except Exception as exc:
            print(f"sess.stop error: {exc!r}", flush=True)
        try:
            _main._print_report(result, state)
        except Exception as exc:
            print(f"report error: {exc!r}", flush=True)
        reactor.stop()
        import sys as _sys
        _sys.exit(0)


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

    _total_timeout = int((config.DURATION_MIN + 1.0) * 60)
    _hard_timer = reactor.callLater(_total_timeout, lambda: (
        print(f"hard timeout after {_total_timeout}s — stopping", flush=True),
        reactor.stop(),
        __import__("sys").exit(0)
    ))
    reactor.run()
