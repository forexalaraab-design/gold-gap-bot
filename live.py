import os
import time
from datetime import datetime, timezone

import config
import gold_price
import main
from cbot import CtraderSession, random_label
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import deferLater
from twisted.internet.threads import deferToThread


def utcnow_iso():
    return main.utcnow_iso()


def _ts_hhmmss(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%H:%M:%S")


@inlineCallbacks
def live_loop():
    token = main.resolve_token()
    state = main.load_state()
    rows = main.load_history()
    print(f"live: starting loop for {config.DURATION_MIN} min "
          f"(global poll every {config.GLOBAL_POLL_SEC}s), mode={config.MODE}")

    sess = CtraderSession()
    result = {"ts": utcnow_iso()}
    try:
        for attempt in (1, 2, 3, 4):
            try:
                yield sess.connect()
                break
            except Exception:
                if attempt == 4:
                    raise
                yield deferLater(reactor, 5, lambda: None)
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
                        import json
                        rf = config.CBOT_REFRESH_TOKEN
                        if not rf and os.path.exists(config.TOKEN_FILE):
                            rf = json.load(open(config.TOKEN_FILE, encoding="utf-8")).get("refreshToken", "")
                        main.sync_tokens(t, rf)
                    except Exception as exc:
                        print("early token sync failed:", exc)
                break
            except Exception as exc:
                auth_err = exc
                print(f"auth attempt {attempt} failed: {exc!r}")
                yield deferLater(reactor, 5, lambda: None)
        if account is None:
            raise auth_err or RuntimeError("authentication failed after retries")
        result["account_id"] = account
        trader = yield sess.get_trader()
        result["balance"] = trader.balance
        result["money_digits"] = trader.moneyDigits
        result["balance_usd"] = (
            trader.balance / (10 ** trader.moneyDigits) if trader.moneyDigits else trader.balance
        )
        symbol_id = yield sess.find_symbol(config.SYMBOL)
        info = yield sess.symbol_info(symbol_id)
        result["symbol_id"] = symbol_id
        result["lot_size"] = info["lotSize"]
        result["volume"] = int(round(config.LOT * info["lotSize"]))
        result["digits"] = info["digits"]

        sess.subscribe_persistent(symbol_id)
        print(f"live: subscribed to symbol {symbol_id}, "
              f"volume={result['volume']}, balance_usd={result['balance_usd']}")

        if config.FORCE_TEST_OPEN and config.ENVIRONMENT.strip().lower() == "demo":
            try:
                bid0, ask0, _ = yield sess.get_spot(symbol_id)
                mid0 = (bid0 + ask0) / 2 / config.SPOT_SCALE
                vol = result["volume"]
                res = yield sess.open_market(
                    symbol_id, "BUY", vol,
                    label=random_label(), comment="")
                print(f"FORCE-TEST OPEN OK orderId={res.order.orderId} "
                      f"positionId={res.position.positionId if res.position else None}")
                if res.position:
                    pid = res.position.positionId
                    entry0 = res.position.price / (10 ** (info["digits"] or 2))
                    print(f"FORCE-TEST entry0={entry0:.2f} digits={info.get('digits')}")
                    pts_scale = 10.0 ** (info.get("digits") or 2)
                    for dist, scale in ((5.0, config.SPOT_SCALE), (5.0, pts_scale),
                                        (0.5, pts_scale), (20.0, pts_scale), (50.0, pts_scale)):
                        try:
                            yield sess.set_sltp(
                                pid,
                                int(round((entry0 - dist) * scale)),
                                int(round((entry0 + dist) * scale)))
                            print(f"FORCE-TEST SETSLTP OK dist={dist} scale={int(scale)}")
                            break
                        except Exception as exc:
                            print(f"FORCE-TEST SETSLTP FAIL dist={dist} scale={int(scale)}: {exc!r}")
                    try:
                        yield sess.close_position(pid)
                        print("FORCE-TEST CLOSE OK")
                    except Exception as exc:
                        print("FORCE-TEST CLOSE FAIL:", repr(exc))
            except Exception as exc:
                print("FORCE-TEST FAIL:", repr(exc))

        end = time.time() + config.DURATION_MIN * 60
        last_save = time.time()
        last_append = 0.0
        last_bal = time.time()
        last_gap = None
        tick_count = 0
        tick_result = {}   # set on first processed tick

        while time.time() < end:
            try:
                global_price, source, source_ts = yield deferToThread(
                    gold_price.get_global_gold_price)
            except Exception as exc:
                print(f"{_ts_hhmmss(time.time())}  global source error: {exc!r}")
                yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                continue

            spot = sess.latest_spot(symbol_id)
            if spot is None:
                print(f"{_ts_hhmmss(time.time())}  no spot tick yet "
                      f"(global={global_price:.2f})")
                yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                continue

            bid, ask, sp_ts = spot
            sp_s = sp_ts / 1000 if sp_ts else 0
            if sp_s and abs(sp_s - time.time()) > 3 * 3600:
                print(f"{_ts_hhmmss(time.time())}  market idle (last tick "
                      f"{_ts_hhmmss(sp_s)})")
                yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)
                continue

            mid = (bid + ask) / 2 / config.SPOT_SCALE
            gap = mid - global_price

            now = time.time()
            changed = last_gap is None or abs(gap - last_gap) >= config.APPEND_TOLERANCE
            if now - last_append >= config.APPEND_EVERY_SEC or changed:
                rows.append({"ts": utcnow_iso(), "global": global_price,
                             "platform": mid, "gap": gap})
                last_append = now
                if len(rows) > config.MAX_HISTORY_ROWS:
                    rows = rows[-config.MAX_HISTORY_ROWS:]
                last_gap = gap

            stats = main.compute_stats(rows[:-1], verbose=False)
            if time.time() - last_bal >= 15:
                try:
                    trad_f = yield sess.get_trader()
                    result["balance"] = trad_f.balance
                    result["balance_usd"] = trad_f.balance / (10 ** result["money_digits"])
                    last_bal = time.time()
                except Exception:
                    pass
            tick_result = {"ts": utcnow_iso(), "symbol_id": symbol_id,
                           "volume": result["volume"],
                           "balance_usd": result["balance_usd"],
                           "global_price": global_price, "source": source,
                           "platform_price": mid, "gap": gap, "stats": stats,
                           "action": "no-op"}
            try:
                yield main.run_trade_cycle(sess, mid, global_price, stats, state,
                                           tick_result)
            except Exception as exc:
                tick_result["action"] = "error"
                tick_result["error"] = repr(exc)
            tick_count += 1
            z = tick_result.get("z")
            zs = f"{z:.2f}" if z is not None else "-"
            if tick_result.get("order"):
                extra = " order=" + json_dumps(tick_result["order"])
            elif tick_result.get("position"):
                extra = " pos=" + json_dumps(tick_result["position"])
            else:
                extra = ""
            print(f"{_ts_hhmmss(now)}  mid={mid:.2f} global={global_price:.2f} "
                  f"gap={gap:.2f} z={zs} action={tick_result.get('action')}"
                  f"{(' err=' + tick_result['error']) if tick_result.get('error') else ''}{extra}")

            if now - last_save >= 30:
                main.save_history(rows)
                state["stats"] = stats
                state["last_run"] = tick_result["ts"]
                main.save_state(state)
                last_save = now

            yield deferLater(reactor, config.GLOBAL_POLL_SEC, lambda: None)

        if tick_result:
            result.update({k: v for k, v in tick_result.items() if v is not None})
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


def json_dumps(obj):
    import json
    return json.dumps(obj)


if __name__ == "__main__":
    d = live_loop()
    d.addErrback(lambda f: print("FATAL", f.getTraceback()))
    reactor.run()