import csv
import json
import os
import time
from datetime import datetime, timezone

import config
import gold_price
import cbot
from cbot import CtraderSession
from ctrader_open_api import Auth
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks


# ============================================================================
# helpers
# ============================================================================

def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_token():
    if config.CBOT_ACCESS_TOKEN:
        token = config.CBOT_ACCESS_TOKEN.strip()
    else:
        if not os.path.exists(config.TOKEN_FILE):
            sys.exit("No token found: set CBOT_ACCESS_TOKEN or run auth_tool.py first")
        with open(config.TOKEN_FILE, encoding="utf-8") as f:
            token = json.load(f).get("accessToken", "")
        if not token:
            sys.exit("token.json has no accessToken")
    return token


def refresh_token():
    refresh = config.CBOT_REFRESH_TOKEN
    if not refresh and os.path.exists(config.TOKEN_FILE):
        refresh = json.load(open(config.TOKEN_FILE, encoding="utf-8")).get("refreshToken", "")
    if not refresh:
        return None
    res = Auth(config.APP_CLIENT_ID.strip(), config.APP_CLIENT_SECRET.strip(),
               config.APP_REDIRECT_URI).refreshToken(refresh)
    new_access = res.get("accessToken") or res.get("access_token")
    if not new_access:
        return None
    try:
        store = config.TOKEN_STORE
        with open(store, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    if os.environ.get("CBOT_TOKEN_SYNC") == "1":
        try:
            sync_tokens(new_access, res.get("refreshToken") or res.get("refresh_token") or refresh)
        except Exception as exc:
            print("token sync failed:", exc)
    return new_access


def sync_tokens(access, refresh):
    import subprocess
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    gh = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    if not repo or not gh:
        return
    env = dict(os.environ, GH_TOKEN=gh)
    for name, value in (("CBOT_ACCESS_TOKEN", access), ("CBOT_REFRESH_TOKEN", refresh)):
        subprocess.run(["gh", "secret", "set", name, "-b", value,
                        "-R", repo], env=env, capture_output=True)
    print("token secrets updated in actions repo")


def load_history():
    rows = []
    if not os.path.exists(config.HISTORY_FILE):
        return rows
    with open(config.HISTORY_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "ts": row["ts"],
                    "global": float(row["global"]),
                    "platform": float(row["platform"]),
                    "gap": float(row["gap"]),
                })
            except (KeyError, ValueError):
                continue
    return rows


def save_history(rows):
    os.makedirs(os.path.dirname(config.HISTORY_FILE), exist_ok=True)
    with open(config.HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ts", "global", "platform", "gap"])
        for r in rows:
            writer.writerow([r["ts"], r["global"], r["platform"], r["gap"]])


def load_state():
    if os.path.exists(config.STATE_FILE):
        try:
            with open(config.STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"position": None, "stats": None}


def save_state(state):
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def compute_stats(rows, verbose=True):
    valid = [r for r in rows if abs(r["gap"]) <= config.MAX_GAP_USD]
    valid = valid[-config.ROLLING_WINDOW:]
    if verbose:
        print(f"stats: valid samples in window = {len(valid)}")
    if len(valid) < config.MIN_SAMPLES:
        return None
    gaps = sorted(r["gap"] for r in valid)
    n = len(gaps)
    mean = sum(gaps) / n
    if n > 1:
        var = sum((g - mean) ** 2 for g in gaps) / (n - 1)
    else:
        var = 0.0
    median = gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2
    mad = sorted(abs(g - median) for g in gaps)[n // 2] * 1.4826 if n else 0.0
    return {"n": n, "mean": mean, "sd": var ** 0.5, "median": median, "mad": mad}


def _to_int(price):
    return int(round(price * config.SPOT_SCALE))


def _to_pt(price, digits):
    return int(round(price * (10.0 ** (digits or 2))))


def in_session(dt):
    if not config.SESSION_GUARD:
        return True
    wd = dt.weekday()
    if wd >= 5:          # Sat / Sun
        return False
    if wd == 4:          # Friday: no entries after 22:20 UTC
        return dt.hour < 22 or (dt.hour == 22 and dt.minute <= 20)
    if wd == 0:          # Monday: skip the first 10 min after reopen
        return not (dt.hour == 0 and dt.minute < 10)
    return True


def _record_close(state, rec):
    trades = state.setdefault("closed_trades", [])
    trades.append(rec)
    if len(trades) > config.MAX_CLOSED_TRADES:
        state["closed_trades"] = trades[-config.MAX_CLOSED_TRADES:]
    try:
        os.makedirs(os.path.dirname(config.TRADES_FILE), exist_ok=True)
        new = not os.path.exists(config.TRADES_FILE)
        with open(config.TRADES_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ts_open", "ts_close", "side", "entry_gap", "close_gap",
                            "entry_price", "close_price", "pnl_units", "pnl_usd",
                            "fees_usd", "pnl_net_usd", "reason"])
            w.writerow([rec.get("ts_open"), rec.get("ts_close"), rec.get("side"),
                        _fmt(rec.get("entry_gap")), _fmt(rec.get("close_gap")),
                        _fmt(rec.get("entry_price")), _fmt(rec.get("close_price")),
                        rec.get("pnl_units"), _fmt(rec.get("pnl_usd")),
                        _fmt(rec.get("fees_usd")), _fmt(rec.get("pnl_net_usd")),
                        rec.get("reason")])
    except Exception as exc:
        print("trades.csv write failed:", exc)
    _write_performance(state)


def _fmt(v):
    return "" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def _write_performance(state):
    trades = state.get("closed_trades") or []
    if not trades:
        return
    pnls = [t.get("pnl_usd", 0.0) for t in trades]
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    eq = 0.0
    peaks = 0.0
    dd = 0.0
    for p in pnls:
        eq += p
        peaks = max(peaks, eq)
        dd = min(dd, eq - peaks)
    perf = {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(100.0 * len(wins) / n, 2),
        "total_pnl_usd": round(sum(pnls), 2),
        "avg_pnl_usd": round(sum(pnls) / n, 3),
        "best_usd": round(max(pnls), 2),
        "worst_usd": round(min(pnls), 2),
        "max_drawdown_usd": round(dd, 2),
        "updated": utcnow_iso(),
    }
    try:
        os.makedirs(os.path.dirname(config.PERF_FILE), exist_ok=True)
        with open(config.PERF_FILE, "w", encoding="utf-8") as f:
            json.dump(perf, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("performance write failed:", exc)


# ============================================================================
# trade logic (lives inside the reactor / session)
# ============================================================================

def position_fees_usd(pos, md):
    """Estimate total cost (commission + swap + spread) for an open position in USD."""
    commission = getattr(pos, "commission", None) or 0
    swap = getattr(pos, "swap", None) or 0
    if md:
        commission = commission / (10 ** md)
        swap = swap / (10 ** md)
    vol_lots = pos.tradeData.volume / 10000.0 if pos.tradeData.volume else 0
    spread_est = config.TRADING_FEES_PER_TRADE_LOT * max(vol_lots, 0.01)
    return commission + swap + spread_est


def dynamic_pnl_usd(pos, mid, digits, md):
    """Live float PnL (dollars), net of fees, at the given mid.

    pos.price arrives as a real dollar float (e.g. 4428.76). volume is in base
    internal units (100 == 0.01 lot). The raw (mid - entry) * volume comes out
    scaled by 10^md (account moneyDigits), same scale as commission, so we
    divide by 10^md to express PnL in real dollars.
    """
    entry = pos.price
    raw = (mid - entry) * pos.tradeData.volume
    if _side_name(pos.tradeData.tradeSide) == "SELL":
        raw = -raw
    gross = raw / (10.0 ** (md or 2))
    fees = position_fees_usd(pos, md)
    return gross - fees, gross, fees

@inlineCallbacks
def run_trade_cycle(sess, mid, global_price, stats, state, result):
    symbol_id = result["symbol_id"]
    try:
        positions = yield sess.open_positions(symbol_id, max_age=120.0)
    except Exception as exc:
        positions = sess.last_positions
        result["open_positions_warn"] = "reconcile-failed:" + repr(exc)
        print("open_positions failed, using cache:", repr(exc))
    result["open_positions"] = len(positions)

    gap = mid - global_price
    result["gap"] = gap
    result["z"] = None
    if stats:
        scale = (stats.get("mad") if config.USE_MAD and stats.get("mad") else 0) or stats["sd"]
        centre = stats["median"] if config.USE_MAD and stats.get("mad") else stats["mean"]
        if scale > 0:
            result["z"] = (gap - centre) / scale

    now_ts = time.time()
    md = state.get("money_digits")
    if not md:
        md = result.get("money_digits") or 2
        state["money_digits"] = md
    entry_units = state.get("entry_balance_units")

    side = None
    action = "none"

    if positions:
        pos = positions[0]
        side_name = _side_name(pos.tradeData.tradeSide)
        digits = result.get("digits") or 2
        net_pnl, gross_pnl, fees = dynamic_pnl_usd(pos, mid, digits, md)
        result["position"] = {
            "positionId": pos.positionId,
            "side": side_name,
            "price": round(float(pos.price), 2),
            "label": pos.tradeData.label,
            "commission_usd": (pos.commission / (10 ** md)) if pos.commission else 0,
            "swap_usd": (pos.swap / (10 ** md)) if pos.swap else 0,
            "pnl_net_usd": round(net_pnl, 2),
            "pnl_gross_usd": round(gross_pnl, 2),
            "fees_usd": round(fees, 2),
        }
        profit_floor = config.DYNAMIC_PROFIT_FLOOR_USD + \
            config.PROFIT_FLOOR_PER_OLOT_USD * (pos.tradeData.volume / 10000.0)
        z_exit_hit = result["z"] is not None and abs(result["z"]) <= config.Z_EXIT

        # --- dynamic profit tracking for the open position -------------------
        # define the persistent position state FIRST so it is never None when we
        # call .get() on it below (this was the NoneType.get crash).
        st_pos = state.setdefault("position", {})
        if not isinstance(st_pos, dict):
            st_pos = {}
            state["position"] = st_pos
        profit_hit = (
            net_pnl >= profit_floor
            and gross_pnl > 0
            and st_pos.get("entry_gap") is not None
        )

        peak = float(st_pos.get("pnl_peak_usd") or net_pnl)
        peak = max(peak, net_pnl)
        st_pos["pnl_peak_usd"] = round(peak, 2)
        st_pos["pnl_last_usd"] = round(net_pnl, 2)
        track = st_pos.setdefault("pnl_track", [])
        track.append(round(net_pnl, 2))
        if len(track) > 120:
            del track[:-120]
        # trailing guard only arms once profit has run up enough, then locks in
        # close when the profit pulls back from its peak by TRAILING_BACK_USD.
        trailing_armed = (
            config.TRAILING_ARM_USD > 0
            and peak >= config.TRAILING_ARM_USD
            and config.TRAILING_BACK_USD > 0
        )
        trailing_hit = trailing_armed and (peak - net_pnl) >= config.TRAILING_BACK_USD
        result["trailing_armed"] = bool(trailing_armed)
        result["pnl_peak_usd"] = round(peak, 2)
        result["profit_floor_usd"] = round(profit_floor, 2)

        # Mean Reversion Close: Close when gap normalizes (z-score near 0)
        # This avoids TRADING_BAD_STOPS issues and works with the gap strategy logic
        mean_revert_close = st_pos is not None and abs(z) < 0.5
        close_now = mean_revert_close
        
        # Legacy trailing/profit logic disabled to avoid conflict; can be re-enabled later
        # close_now = z_exit_hit or (profit_hit and not trailing_armed) or trailing_hit
        if close_now:
            try:
                yield sess.close_position(pos.positionId)
                close_ok = True
            except Exception as exc:
                close_ok = False
                result["close_failed"] = repr(exc)
                print("close_position failed (will retry next tick):", repr(exc))
            if close_ok:
                try:
                    trad_end = yield sess.get_trader()
                    pnl_units = (trad_end.balance - entry_units) / (10 ** md) if entry_units is not None else None
                except Exception:
                    pnl_units = None
                close_gap = mid - global_price
                reason = "mean_revert"  # using the new mean reversion close method
                _record_close(state, {
                    "ts_open": st_pos.get("opened_at"),
                    "ts_close": utcnow_iso(),
                    "side": side_name,
                    "entry_gap": st_pos.get("entry_gap"),
                    "close_gap": close_gap,
                    "entry_price": st_pos.get("entry_price"),
                    "close_price": mid,
                    "pnl_units": pnl_units,
                    "pnl_usd": pnl_units,
                    "reason": reason,
                    "pnl_net_usd": round(net_pnl, 2),
                    "fees_usd": round(fees, 2),
                    "pnl_peak_usd": round(peak, 2),
                })
                result["close_pnl_usd"] = pnl_units
                result["action"] = "close:" + reason
                state["position"] = None
                state["cooldown_until"] = now_ts + config.COOLDOWN_MINUTES * 60
            else:
                result["action"] = "close_pending"
        else:
            result["action"] = "hold"
    else:
        if state.get("position") is not None and entry_units is not None:
            try:
                trad = yield sess.get_trader()
                pnl_units = (trad.balance - entry_units) / (10 ** md)
                _record_close(state, {
                    "ts_open": state["position"].get("opened_at"),
                    "ts_close": utcnow_iso(),
                    "side": state["position"].get("side"),
                    "entry_gap": state["position"].get("entry_gap"),
                    "close_gap": gap,
                    "entry_price": state["position"].get("entry_price"),
                    "close_price": mid,
                    "pnl_units": pnl_units,
                    "pnl_usd": pnl_units,
                    "reason": "stopped_or_external",
                })
                result["close_pnl_usd"] = pnl_units
                result["action"] = "external_close"
            except Exception as exc:
                result["action"] = "external_close(no_pnl: " + repr(exc) + ")"
            state["position"] = None
            state.setdefault("closed_trades", [])
        state["position"] = None

        cooldown_left = state.get("cooldown_until", 0) - now_ts
        in_session_now = in_session(datetime.now(timezone.utc))

        can_trade = (
            config.MODE == "trade"
            and stats is not None
            and result["z"] is not None
            and abs(result["z"]) >= config.Z_ENTRY
            and abs(gap) <= config.MAX_ENTRY_GAP_USD
            and result.get("balance_usd", 0) >= config.MIN_BALANCE_TO_TRADE
            and cooldown_left <= 0
            and in_session_now
        )
        if can_trade:
            # hard guard: never double-open. The `positions`/last_positions
            # cache is kept truthful (updated on our own open/close), so we
            # never send a fresh (slow, blocking) reconcile here just to
            # confirm emptiness — a timeout there is what froze the loop and
            # stopped closes entirely.
            if positions:
                result["action"] = "hold:already_open"
                result["open_positions"] = len(positions)
            else:
                side = "SELL" if gap > 0 else "BUY"
                sd = stats.get("mad") if config.USE_MAD else stats["sd"]
                sd = sd or stats["sd"]
                sl_dist = max(config.SL_AFTER_ENTRY_USD, (config.Z_STOP - config.Z_ENTRY) * sd)
                min_tp_dist = max(0.3 * sd, 1.0)
                if side == "SELL":
                    sl = mid + sl_dist
                    tp = min(mid - min_tp_dist, mid - 0.9 * abs(gap))
                else:
                    sl = mid - sl_dist
                    tp = max(mid + min_tp_dist, mid + 0.9 * abs(gap))
                print(f"order-request side={side} mid={mid:.2f} sl={sl:.2f} tp={tp:.2f} sl_dist={sl_dist:.2f} "
                      f"gap={gap:.2f} tp_dist={(mid - tp) if side == 'SELL' else (tp - mid):.2f}")
                try:
                    trad_pre = yield sess.get_trader()
                except Exception:
                    trad_pre = None
                vol = result["volume"]
                res = yield sess.open_market(
                    symbol_id, side, vol,
                    sl=_to_int(sl),
                    tp=_to_int(tp),
                    label=cbot.random_label(),
                    comment="")
                order = res.order
                result["action"] = "open:" + side
                result["order"] = {
                    "orderId": order.orderId,
                    "side": side,
                    "executionPrice": order.executionPrice if order.executionPrice else None,
                    "tradeData": {"volume": order.tradeData.volume, "label": order.tradeData.label},
                }
                state["position"] = {
                    "positionId": res.position.positionId if res.position else None,
                    "side": side,
                    "entry_gap": gap,
                    "entry_price": (order.executionPrice / config.SPOT_SCALE) if order.executionPrice else None,
                    "opened_at": utcnow_iso(),
                }
                state["entry_balance_units"] = trad_pre.balance if trad_pre is not None else None
                state["cooldown_until"] = 0
        else:
            reason = "no_signal"
            if config.MODE != "trade":
                reason = "mode!=trade"
            elif stats is None:
                reason = "warmup"
            elif result["z"] is not None and abs(result["z"]) < config.Z_ENTRY:
                reason = "z_below_entry"
            elif abs(gap) > config.MAX_ENTRY_GAP_USD:
                reason = "gap_above_cap"
            elif result.get("balance_usd", 0) < config.MIN_BALANCE_TO_TRADE:
                reason = "balance_low"
            elif cooldown_left > 0:
                reason = "cooldown_min"
            elif not in_session_now:
                reason = "session_closed"
            result["action"] = "none:" + reason
    return action


def _side_name(trade_side):
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as Models
    for name, num in Models.ProtoOATradeSide.DESCRIPTOR.values_by_name.items():
        if num == trade_side:
            return name
    return str(trade_side)


# ============================================================================
# main entry
# ============================================================================

def main():
    token = resolve_token()
    state = load_state()
    rows = load_history()

    # stats built from history EXCLUDING this tick (what we knew before now)
    stats = compute_stats(rows)
    result = {"ts": utcnow_iso(), "stats": stats, "stats_used": stats is not None}

    try:
        global_price, source, source_ts = gold_price.get_global_gold_price()
        result["global_price"] = global_price
        result["source"] = source
    except Exception as exc:
        result["error"] = "global-source: " + repr(exc)
        _finish(result, rows, state)
        return

    @inlineCallbacks
    def flow():
        sess = CtraderSession()
        try:
            for attempt in (1, 2):
                try:
                    yield sess.connect()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    from twisted.internet.task import deferLater
                    yield deferLater(reactor, 5, lambda: None)
            try:
                account = yield sess.authenticate(token)
            except Exception:
                refreshed = refresh_token()
                if not refreshed:
                    raise
                yield sess.connect()
                account = yield sess.authenticate(refreshed)
            result["account_id"] = account
            trader = yield sess.get_trader()
            result["balance"] = trader.balance
            result["money_digits"] = trader.moneyDigits
            state["money_digits"] = trader.moneyDigits
            result["balance_usd"] = (
                trader.balance / (10 ** trader.moneyDigits) if trader.moneyDigits else trader.balance
            )
            result["deposit_asset"] = trader.depositAssetId
            symbol_id = yield sess.find_symbol(config.SYMBOL)
            info = yield sess.symbol_info(symbol_id)
            result["symbol_id"] = symbol_id
            result["digits"] = info["digits"]
            result["lot_size"] = info["lotSize"]
            result["min_volume"] = info["minVolume"]
            result["volume"] = int(round(config.LOT * info["lotSize"]))
            result["min_volume"] = info["minVolume"]
            bid, ask, sp_ts = yield sess.get_spot(symbol_id)
            result["bid"] = bid / config.SPOT_SCALE
            result["ask"] = ask / config.SPOT_SCALE
            mid = (bid + ask) / 2 / config.SPOT_SCALE
            result["platform_price"] = mid
            yield run_trade_cycle(sess, mid, global_price, stats, state, result)
            result["ok"] = True
        except Exception:
            import traceback
            result["error"] = traceback.format_exc(limit=25)
        finally:
            sess.stop()

    d = flow()

    @d.addBoth
    def _flush(_):
        # record observation then persist
        if "global_price" in result and "platform_price" in result:
            rows.append({
                "ts": result["ts"],
                "global": result["global_price"],
                "platform": result["platform_price"],
                "gap": result["platform_price"] - result["global_price"],
            })
            save_history(rows)
        state["stats"] = stats
        state["last_run"] = result["ts"]
        save_state(state)
        _print_report(result, state)
        reactor.stop()

    reactor.run()


def _print_report(result, state):
    print("=" * 50)
    print("OPERATIONS REPORT")
    print("=" * 50)
    for k in ("ts", "account_id", "balance", "balance_usd", "deposit_asset",
              "symbol_id", "digits", "bid", "ask", "platform_price",
              "global_price", "source", "gap", "z", "action", "ok"):
        if k in result:
            print(f"  {k:16s}: {result[k]}")
    if result.get("stats"):
        st = result["stats"]
        print(f"  centre/scale      : {st['mean']:.2f} / {st['sd']:.2f}")
        if "mad" in st:
            print(f"  median/mad        : {st['median']:.2f} / {st['mad']:.2f}")
    if result.get("close_pnl_usd") is not None:
        print(f"  close_pnl_usd     : {result['close_pnl_usd']:.3f}")
    trades = state.get("closed_trades") or []
    if trades:
        print(f"  closed_trades     : {len(trades)} (last pnl={trades[-1].get('pnl_usd')})")
        import os as _os
        if _os.path.exists(config.PERF_FILE):
            try:
                with open(config.PERF_FILE, encoding="utf-8") as f:
                    perf = json.load(f)
                print("  perf              :", json.dumps(perf, ensure_ascii=False))
            except Exception:
                pass
    if result.get("error"):
        print("  ERROR             :", result["error"])
    if result.get("order"):
        print("  order             :", json.dumps(result["order"]))
    if result.get("position"):
        print("  position          :", json.dumps(result["position"]))
    if state.get("position"):
        print("  state.position    :", json.dumps(state["position"], ensure_ascii=False))
    if result.get("trailing_armed"):
        print(f"  trailing armed    : peak={result.get('pnl_peak_usd')} "
              f"back={config.TRAILING_BACK_USD}")
    print("=" * 50)


def _finish(result, rows, state):
    state["stats"] = result.get("stats")
    state["last_run"] = result.get("ts") or utcnow_iso()
    save_state(state)
    _print_report(result, state)


if __name__ == "__main__":
    main()