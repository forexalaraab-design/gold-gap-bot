import csv
import json
import os
import sys
from datetime import datetime, timezone

import config
import gold_price
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
    return new_access


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
    gaps = [r["gap"] for r in valid]
    n = len(gaps)
    mean = sum(gaps) / n
    if n > 1:
        var = sum((g - mean) ** 2 for g in gaps) / (n - 1)
    else:
        var = 0.0
    sd = var ** 0.5
    return {"n": n, "mean": mean, "sd": sd}


def _to_int(price):
    return int(round(price * config.SPOT_SCALE))


# ============================================================================
# trade logic (lives inside the reactor / session)
# ============================================================================

@inlineCallbacks
def run_trade_cycle(sess, mid, global_price, stats, state, result):
    symbol_id = result["symbol_id"]
    positions = yield sess.open_positions(symbol_id)
    result["open_positions"] = len(positions)

    gap = mid - global_price
    result["gap"] = gap
    result["z"] = None
    if stats and stats["sd"] > 0:
        result["z"] = (gap - stats["mean"]) / stats["sd"]

    side = None
    action = "none"

    if positions:
        pos = positions[0]
        result["position"] = {
            "positionId": pos.positionId,
            "side": _side_name(pos.tradeData.tradeSide),
            "price": pos.price,
            "label": pos.tradeData.label,
        }
        if result["z"] is not None and abs(result["z"]) <= config.Z_EXIT:
            yield sess.close_position(pos.positionId)
            result["action"] = "close"
            state["position"] = None
        else:
            result["action"] = "hold"
    else:
        state["position"] = None
        can_trade = (
            config.MODE == "trade"
            and stats is not None
            and result["z"] is not None
            and abs(result["z"]) >= config.Z_ENTRY
            and abs(gap) <= config.MAX_ENTRY_GAP_USD
            and result.get("balance_usd", 0) >= config.MIN_BALANCE_TO_TRADE
        )
        if can_trade:
            side = "SELL" if gap > 0 else "BUY"
            sl_dist = max(config.SL_AFTER_ENTRY_USD, (config.Z_STOP - config.Z_ENTRY) * stats["sd"]) if stats["sd"] > 0 else config.SL_AFTER_ENTRY_USD
            if side == "SELL":
                tp = mid - 0.9 * gap
                sl = mid + sl_dist
            else:
                tp = mid - 0.9 * gap
                sl = mid - sl_dist
            vol = result["volume"]
            res = yield sess.open_market(
                symbol_id, side, vol,
                sl=_to_int(sl),
                tp=_to_int(tp),
                label="GAPBOT", comment="gap=" + format(gap, ".2f"))
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
                "opened_at": utcnow_iso(),
            }
        else:
            reason = "no_signal"
            if config.MODE != "trade":
                reason = "mode!=trade"
            elif stats is None:
                reason = "warmup(not enough samples)"
            elif result["z"] is not None and abs(result["z"]) < config.Z_ENTRY:
                reason = "z_below_entry"
            elif abs(gap) > config.MAX_ENTRY_GAP_USD:
                reason = "gap_above_cap"
            elif result.get("balance_usd", 0) < config.MIN_BALANCE_TO_TRADE:
                reason = "balance_low"
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
    print("GOLD GAP BOT - run report")
    print("=" * 50)
    for k in ("ts", "account_id", "balance", "balance_usd", "deposit_asset",
              "symbol_id", "digits", "bid", "ask", "platform_price",
              "global_price", "source", "gap", "z", "action", "ok"):
        if k in result:
            print(f"  {k:16s}: {result[k]}")
    if result.get("stats"):
        st = result["stats"]
        print(f"  mean/sd           : {st['mean']:.2f} / {st['sd']:.2f}")
    if result.get("error"):
        print("  ERROR             :", result["error"])
    if result.get("order"):
        print("  order             :", json.dumps(result["order"]))
    if result.get("position"):
        print("  position          :", json.dumps(result["position"]))
    if state.get("position"):
        print("  state.position    :", json.dumps(state["position"], ensure_ascii=False))
    print("=" * 50)


def _finish(result, rows, state):
    state["stats"] = result.get("stats")
    state["last_run"] = result.get("ts") or utcnow_iso()
    save_state(state)
    _print_report(result, state)


if __name__ == "__main__":
    main()