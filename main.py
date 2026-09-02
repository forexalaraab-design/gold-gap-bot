#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — استراتيجية احترافية مع إغلاق متعدد الطبقات
تغييرات رئيسية:
  1. تحسين حساب PnL مع اعتبار البحر темпераيا (CFDs)
  2. الطبقة 1: إغلاق عند الوصول للذروة المطلقة + تراجع (Trailing)
  3. الطبقة 2: إغلاق عند وصول الخسارة للحد الأقصى (Max Loss)
  4. الطبقة 3: إغلاق عند تجاوز المدة القصوى (Max Hold Time)
  5. الطبقة 4: دائرة أمان Daily Loss ومتتالية الخسائر
  6. الطبقة 5: إغلاق عند عودة الفجوة لـ Z_EXIT أو تجاوز Z_STOP
  7. حفظ state شمولي يشمل كل الطبقات وبيانات الأداء
"""

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
            raise RuntimeError(
                "No token found: set CBOT_ACCESS_TOKEN or run auth_tool.py first"
            )
        with open(config.TOKEN_FILE, encoding="utf-8") as f:
            token = json.load(f).get("accessToken", "")
        if not token:
            raise RuntimeError("token.json has no accessToken")
    return token


def refresh_token():
    refresh = config.CBOT_REFRESH_TOKEN
    if not refresh and os.path.exists(config.TOKEN_FILE):
        refresh = json.load(open(config.TOKEN_FILE, encoding="utf-8")).get(
            "refreshToken", ""
        )
    if not refresh:
        return None
    res = Auth(
        config.APP_CLIENT_ID.strip(), config.APP_CLIENT_SECRET.strip(),
        config.APP_REDIRECT_URI
    ).refreshToken(refresh)
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
            sync_tokens(
                new_access,
                res.get("refreshToken") or res.get("refresh_token") or refresh,
            )
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
    for name, value in (
        ("CBOT_ACCESS_TOKEN", access),
        ("CBOT_REFRESH_TOKEN", refresh),
    ):
        subprocess.run(
            ["gh", "secret", "set", name, "-b", value, "-R", repo],
            env=env, capture_output=True,
        )
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
            writer.writerow(
                [r["ts"], r["global"], r["platform"], r["gap"]]
            )


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
    median = (
        gaps[n // 2]
        if n % 2
        else (gaps[n // 2 - 1] + gaps[n // 2]) / 2
    )
    mad = (
        sorted(abs(g - median) for g in gaps)[n // 2] * 1.4826
        if n
        else 0.0
    )
    return {"n": n, "mean": mean, "sd": var ** 0.5,
            "median": median, "mad": mad}


def _to_int(price):
    return int(round(price * config.SPOT_SCALE))


def _to_pt(price, digits):
    return int(round(price * (10.0 ** (digits or 2))))


def in_session(dt):
    if not config.SESSION_GUARD:
        return True
    wd = dt.weekday()
    if wd >= 5:  # Sat / Sun
        return False
    if wd == 4:  # Friday: no entries after 22:20 UTC
        return dt.hour < 22 or (dt.hour == 22 and dt.minute <= 20)
    if wd == 0:  # Monday: skip the first 10 min after reopen
        return not (dt.hour == 0 and dt.minute < 10)
    return True


def _side_name(trade_side):
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as Models
    for name, num in Models.ProtoOATradeSide.DESCRIPTOR.values_by_name.items():
        if num == trade_side:
            return name
    return str(trade_side)


def position_fees_usd(pos, md):
    """تكلفة الصفقة الإجمالية (عمولة + س왑 + spread مقدر)."""
    commission = getattr(pos, "commission", None) or 0
    swap = getattr(pos, "swap", None) or 0
    if md:
        commission = commission / (10 ** md)
        swap = swap / (10 ** md)
    vol_lots = pos.tradeData.volume / 10000.0 if pos.tradeData.volume else 0
    spread_est = config.TRADING_FEES_PER_TRADE_LOT * max(vol_lots, 0.01)
    return commission + swap + spread_est


def dynamic_pnl_usd(pos, mid, digits, md):
    """PnL صافي (بعد الرسوم) من mid الحالي والصفقة المفتوحة."""
    entry = pos.price
    if entry is None or entry == 0:
        # إصلاح: إذا entry price مناطق، استخدم st_pos أو احسب من gap
        return 0.0, 0.0, 0.0
    raw = (mid - entry) * pos.tradeData.volume
    if _side_name(pos.tradeData.tradeSide) == "SELL":
        raw = -raw
    gross = raw / (10.0 ** (md or 2))
    fees = position_fees_usd(pos, md)
    return gross - fees, gross, fees


# ============================================================================
# قنوات إغلاق متعددة الطبقات
# ============================================================================


class ClosingManager:
    """يدير 5 طبقات إغلاق ويتخذ القرار النهائي."""

    def __init__(self, state, config_obj):
        self.state = state
        self.cfg = config_obj
        # إحصائيات الأداء المتراكمة
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.trade_count_today = 0

    def init_from_state(self, state):
        """استعادة إحصائيات الأداء من state."""
        perf = state.get("perf", {})
        self.daily_pnl = perf.get("running_daily_pnl", 0.0)
        self.consecutive_losses = perf.get("consecutive_losses", 0)
        self.trade_count_today = perf.get("trades_today", 0)

    def save_perf_to_state(self, state):
        """حفظ إحصائيات الأداء في state."""
        state["perf"] = {
            "running_daily_pnl": round(self.daily_pnl, 2),
            "consecutive_losses": self.consecutive_losses,
            "trades_today": self.trade_count_today,
            "last_updated": utcnow_iso(),
        }

    def can_trade_today(self):
        """التحقق مما إذا كان يمكن فتح صفقة اليوم (دائرة أمان Daily Loss)."""
        if self.daily_pnl <= -self.cfg.MAX_DAILY_LOSS_USD:
            return False
        if self.consecutive_losses >= self.cfg.MAX_CONSECUTIVE_LOSSES:
            return False
        return True

    def record_loss(self):
        """تسجيل خسارة وتحديث العدادات."""
        self.consecutive_losses += 1
        self.trade_count_today += 1
        self.daily_pnl -= 1  # تقريب

    def record_win(self):
        """تسجيل ربح وإعادة تعيين عداد الخسائر."""
        self.consecutive_losses = 0
        self.trade_count_today += 1
        self.daily_pnl += 1  # تقريب

    def check_close(self, position, mid, global_price, stats,
                    st_pos, now, money_digits):
        """فحص جميع طبقات الإغلاق واقتراح الإغلاق إن لزم.

        يُرجع (should_close: bool, reason: str or None)
        """
        side_name = _side_name(position.tradeData.tradeSide)
        digits = getattr(position, "digits", 2) or 2
        net_pnl, gross_pnl, fees = dynamic_pnl_usd(position, mid,
                                                     digits, money_digits)
        entry_gap = st_pos.get("entry_gap")
        entry_price = st_pos.get("entry_price")
        opened_at = st_pos.get("opened_at")

        # طพวกติดตามกำไร
        peak = float(st_pos.get("pnl_peak_usd") or net_pnl)
        peak = max(peak, net_pnl)

        # --- الطبقة 1: إغلاق بالربح (Trailing) ---
        # تفعيل الترهل: profit >= TRAILING_ARM_USD
        trailing_armed = (
            self.cfg.TRAILING_ARM_USD > 0
            and peak >= self.cfg.TRAILING_ARM_USD
            and self.cfg.TRAILING_BACK_USD > 0
        )
        trailing_hit = trailing_armed and (peak - net_pnl) >= self.cfg.TRAILING_BACK_USD
        if trailing_hit:
            return True, "trailing"

        # --- الطبقة 2: الحد الأقصى للخسارة (Max Loss) ---
        if net_pnl <= -self.cfg.MAX_LOSS_USD:
            return True, "max_loss"

        # --- الطبقة 3: الحد الأقصى للزمن (Max Hold) ---
        if opened_at:
            opened_dt = datetime.fromisoformat(opened_at)
            open_hours = (now - opened_dt.timestamp()) / 3600.0
            if open_hours >= self.cfg.MAX_HOLD_HOURS:
                return True, "max_hold_time"

        # --- الطبقة 4: عودة الفجوة (Mean Reversion) ---
        # إغلاق إذا عاد z للقرب من الصفر (Z_EXIT) أو إذا تجاوزت الفجوة الحد الأقصى
        if stats:
            scale = (stats.get("mad") if self.cfg.USE_MAD and stats.get("mad") else 0) or stats["sd"]
            centre = stats["median"] if self.cfg.USE_MAD and stats.get("mad") else stats["mean"]
            if scale > 0:
                z = (global_price - entry_price) / scale if entry_price else None
                if z is not None and abs(z) <= self.cfg.Z_EXIT:
                    return True, "z_revert"
        if entry_price and abs(global_price - entry_price) >= self.cfg.MAX_ENTRY_GAP_USD:
            return True, "gap_exceeded_cap"

        # --- الطبقة 4b: إغلاق فوري إذا تجاوزت الفجوة نسبة مئوية من السعر (Gap Cap Pct) ---
        if entry_price and entry_price > 0:
            gap_pct = abs(global_price - entry_price) / entry_price
            if gap_pct >= self.cfg.gap_max_gap_pct:
                return True, "gap_cap_pct"

        # --- الطبقة 5: Daily Loss / Consecutive Losses Circuit Breaker ---
        # لا تطبق هنا لأنها تؤثر على الفتح وليس الإغلاق

        st_pos["pnl_peak_usd"] = round(peak, 2)
        st_pos["pnl_last_usd"] = round(net_pnl, 2)
        track = st_pos.setdefault("pnl_track", [])
        track.append(round(net_pnl, 2))
        if len(track) > 120:
            del track[:-120]

        return False, None

    def record_close(self, state, win):
        """تسجيل نتائج الصفقة المغلقة."""
        if win:
            self.record_win()
        else:
            self.record_loss()
        self.save_perf_to_state(state)


# ============================================================================
# trade logic
# ============================================================================


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
                w.writerow([
                    "ts_open", "ts_close", "side", "entry_gap", "close_gap",
                    "entry_price", "close_price", "pnl_units", "pnl_usd",
                    "fees_usd", "pnl_net_usd", "reason",
                ])
            w.writerow([
                rec.get("ts_open"), rec.get("ts_close"), rec.get("side"),
                _fmt(rec.get("entry_gap")), _fmt(rec.get("close_gap")),
                _fmt(rec.get("entry_price")), _fmt(rec.get("close_price")),
                rec.get("pnl_units"), _fmt(rec.get("pnl_usd")),
                _fmt(rec.get("fees_usd")), _fmt(rec.get("pnl_net_usd")),
                rec.get("reason"),
            ])
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


@inlineCallbacks
def run_trade_cycle(sess, mid, global_price, stats, state, result,
                     closing_mgr):
    """الدورة الرئيسية للتداول مع فحص جميع طبقات الإغلاق."""
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
        scale = (
            stats.get("mad") if config.USE_MAD and stats.get("mad") else 0
        ) or stats["sd"]
        centre = (
            stats["median"] if config.USE_MAD and stats.get("mad") else stats["mean"]
        )
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
    closed_this_cycle = False

    # --- إذا كانت هناك صفقة مفتوحة: فحص جميع طبقات الإغلاق ---
    if positions:
        pos = positions[0]
        st_pos = state.get("position")
        if st_pos is None:
            st_pos = {}
            state["position"] = st_pos
        if not isinstance(st_pos, dict):
            st_pos = {}
            state["position"] = st_pos

        # فحص الطبقات الخمس للإغلاق
        should_close, close_reason = closing_mgr.check_close(
            pos, mid, global_price, stats, st_pos, now_ts, md,
        )
        result["close_check"] = {
            "should_close": should_close,
            "reason": close_reason,
        }

        if should_close and close_reason:
            try:
                # إغلاق نشط
                yield sess.close_position(
                    pos.positionId,
                    volume=getattr(pos.tradeData, "volume", None),
                    max_retries=3,
                )
                closed_this_cycle = True

                # حساب PnL الحقيقي من حركة السعر (ليس من رصيد الحساب)
                # PnL = (السعر النهائي - سعر الفتح) × الحجم × الاتجاه
                # للـ BUY: PnL = (mid - entry) * volume
                # للـ SELL: PnL = (entry - mid) * volume
                entry_price = st_pos.get("entry_price")
                close_price = mid  # سعر الإغلاق الحالي
                side_name = _side_name(pos.tradeData.tradeSide)
                volume = getattr(pos.tradeData, "volume", None)
                if volume is not None and volume != 0:
                    # تحويل الـ volume إلى وحدات صحيحة:
                    # cTrader XAUUSD 0.01 لوت = 1 أونصة ذهب
                    # الـ volume قد يكون 100 (وحدات داخلية) أو 0.01 (لوت)
                    if volume <= 1:
                        unit_volume = volume * 100  # من لوت إلى وحدات داخلية
                    else:
                        unit_volume = volume  # بالفعل وحدات داخلية
                    # PnL = حركة السعر × الوحدات / SPOT_SCALE
                    spot_scale = config.SPOT_SCALE or 100000.0
                    price_diff = close_price - entry_price if entry_price else 0
                    if side_name == "SELL":
                        price_diff = -price_diff
                    raw_pnl = (price_diff * unit_volume) / spot_scale
                    fees_est = position_fees_usd(pos, md) if md else 0
                    pnl_net = round(raw_pnl - fees_est, 2)
                    pnl_gross = round(raw_pnl, 2)
                    print(f"  [PnL calc] vol={volume} → unit={unit_volume}, "
                          f"diff={price_diff:.2f}, raw={raw_pnl:.4f}, "
                          f"fees={fees_est:.2f}, net=${pnl_net}")
                else:
                    # volume غير متوفر — نعود لحساب dynamic_pnl_usd
                    net_pnl, gross_pnl, fees = dynamic_pnl_usd(pos, mid, md, md)
                    pnl_net = net_pnl
                    pnl_gross = gross_pnl
                    fees = 0.0
                    print(f"  [PnL calc] volume=None → فالينغ باك إلى dynamic_pnl_usd")
                result["action"] = "close:" + close_reason
                state["position"] = None
                state["cooldown_until"] = now_ts + config.COOLDOWN_MINUTES * 60
                print(
                    f"✓ CLOSED (layer: {close_reason}): "
                    f"pnl={net_pnl:.2f} USD (gross={pnl_gross:.2f}), "
                    f"peak={float(st_pos.get('pnl_peak_usd', 0)):.2f} USD"
                )
                if net_pnl > 0:
                    closing_mgr.record_win()
                else:
                    closing_mgr.record_loss()
                closing_mgr.save_perf_to_state(state)
                _record_close(state, {
                    "ts_open": st_pos.get("opened_at"),
                    "ts_close": utcnow_iso(),
                    "side": side_name,
                    "entry_gap": st_pos.get("entry_gap"),
                    "close_gap": gap,
                    "entry_price": entry_price,
                    "close_price": close_price,
                    "pnl_units": net_pnl,
                    "pnl_usd": net_pnl,
                    "fees_usd": round(fees, 2),
                    "pnl_net_usd": round(net_pnl, 2),
                    "reason": close_reason,
                    "pnl_peak_usd": round(
                        float(st_pos.get("pnl_peak_usd") or 0), 2,
                    ),
                })
                result["close_pnl_usd"] = net_pnl
            except Exception as exc:
                result["close_failed"] = repr(exc)
                print(f"close_position failed (layer: {close_reason}): {exc!r}")
                result["action"] = "close_pending"
        else:
            result["action"] = "hold"
    else:
        # لا توجد صفقة مفتوحة — التأكد من أن state نظيفة
        state["position"] = None

    # --- إذا لم تكن هناك صفقة مفتوحة: اتخاذ قرار الفتح ---
    if not positions and not closed_this_cycle:
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
            if positions:
                result["action"] = "hold:already_open"
                result["open_positions"] = len(positions)
            else:
                # --- فتح صفقة جديدة ---
                side = "SELL" if gap > 0 else "BUY"
                sd = (
                    stats.get("mad") if config.USE_MAD
                    else stats["sd"]
                )
                sd = sd or stats["sd"]
                sl_dist = max(
                    config.SL_AFTER_ENTRY_USD,
                    (config.Z_STOP - config.Z_ENTRY) * sd,
                )
                min_tp_dist = max(0.3 * sd, 1.0)
                if side == "SELL":
                    sl = mid + sl_dist
                    tp = min(mid - min_tp_dist, mid - 0.9 * abs(gap))
                else:
                    sl = mid - sl_dist
                    tp = max(mid + min_tp_dist, mid + 0.9 * abs(gap))
                print(
                    f"order-request side={side} mid={mid:.2f} "
                    f"sl={sl:.2f} tp={tp:.2f} sl_dist={sl_dist:.2f} "
                    f"gap={gap:.2f} tp_dist={(mid - tp) if side == 'SELL' else (tp - mid):.2f}"
                )
                try:
                    trad_pre = yield sess.get_trader()
                except Exception:
                    trad_pre = None
                vol = result["volume"]
                res = yield sess.open_market(
                    symbol_id, side, vol,
                    sl=_to_int(sl), tp=_to_int(tp),
                    label=cbot.random_label(),
                    comment="",
                )
                order = res.order
                result["action"] = "open:" + side
                result["order"] = {
                    "orderId": order.orderId,
                    "side": side,
                    "executionPrice": order.executionPrice
                    if order.executionPrice else None,
                    "tradeData": {
                        "volume": order.tradeData.volume,
                        "label": order.tradeData.label,
                    },
                }
                new_st_pos = {
                    "positionId": res.position.positionId
                    if res.position else None,
                    "side": side,
                    "entry_gap": gap,
                    "entry_price": (
                        float(res.position.price)
                        if (res.position is not None
                            and hasattr(res.position, "price")
                            and res.position.price is not None
                            and float(res.position.price) != 0.0)
                        else None
                    ),
                    "opened_at": utcnow_iso(),
                    "pnl_peak_usd": 0.0,
                    "pnl_track": [],
                }
                state["position"] = new_st_pos
                state["entry_balance_units"] = (
                    trad_pre.balance if trad_pre is not None else None
                )
                state["cooldown_until"] = 0
                # تحديث الأداء
                closing_mgr.trade_count_today += 1
                closing_mgr.save_perf_to_state(state)
        else:
            reasons = []
            if config.MODE != "trade":
                reasons.append("mode!=trade")
            if stats is None:
                reasons.append("warmup")
            elif result["z"] is not None and abs(result["z"]) < config.Z_ENTRY:
                reasons.append("z_below_entry")
            if abs(gap) > config.MAX_ENTRY_GAP_USD:
                reasons.append("gap_above_cap")
            if result.get("balance_usd", 0) < config.MIN_BALANCE_TO_TRADE:
                reasons.append("balance_low")
            if cooldown_left > 0:
                reasons.append("cooldown_min")
            if not in_session_now:
                reasons.append("session_closed")
            # دائرة Daily Loss و Consecutive Losses
            if not closing_mgr.can_trade_today():
                reasons.append("circuit_breaker")
            result["action"] = "none:" + ",".join(reasons) if reasons else "none"

    return action


# ============================================================================
# main entry
# ============================================================================

def main():
    token = resolve_token()
    state = load_state()
    rows = load_history()

    stats = compute_stats(rows)

    result = {
        "ts": utcnow_iso(),
        "stats": stats,
        "stats_used": stats is not None,
    }

    closing_mgr = ClosingManager(state, config)
    closing_mgr.init_from_state(state)

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
                trader.balance / (10 ** trader.moneyDigits)
                if trader.moneyDigits
                else trader.balance
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
            yield run_trade_cycle(
                sess, mid, global_price, stats, state, result,
                closing_mgr,
            )
            result["ok"] = True
        except Exception:
            import traceback
            result["error"] = traceback.format_exc(limit=25)
        finally:
            sess.stop()

    d = flow()

    @d.addBoth
    def _flush(_):
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
    for k in (
        "ts", "account_id", "balance", "balance_usd", "deposit_asset",
        "symbol_id", "digits", "bid", "ask", "platform_price",
        "global_price", "source", "gap", "z", "action", "ok",
    ):
        if k in result:
            print(f"  {k:16s}: {result[k]}")
    if result.get("stats"):
        st = result["stats"]
        print(f"  centre/scale      : {st['mean']:.2f} / {st['sd']:.2f}")
        if "mad" in st:
            print(f"  median/mad        : {st['median']:.2f} / {st['mad']:.2f}")
    if result.get("close_pnl_usd") is not None:
        print(f"  close_pnl_usd     : {result['close_pnl_usd']:.3f}")
    if result.get("close_check"):
        cc = result["close_check"]
        print(f"  close_check       : should={cc['should_close']}, reason={cc['reason']}")
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
    perf = state.get("perf")
    if perf:
        print(f"  DAILY P&L        : {perf.get('running_daily_pnl', 'N/A')} USD")
        print(f"  CONSECUTIVE LOSS : {perf.get('consecutive_losses', 'N/A')}")
        print(f"  TRADES TODAY     : {perf.get('trades_today', 'N/A')}")
    if result.get("error"):
        print("  ERROR             :", result["error"])
    if result.get("order"):
        print("  order             :", json.dumps(result["order"]))
    if result.get("position"):
        print("  position          :", json.dumps(result["position"], ensure_ascii=False))
    if state.get("position"):
        print(
            "  state.position    :",
            json.dumps(state["position"], ensure_ascii=False),
        )
    if result.get("trailing_armed"):
        print(
            f"  trailing armed    : peak={result.get('pnl_peak_usd')} "
            f"back={config.TRAILING_BACK_USD}"
        )
    print("=" * 50)


def _finish(result, rows, state):
    state["stats"] = result.get("stats")
    state["last_run"] = result.get("ts") or utcnow_iso()
    save_state(state)
    _print_report(result, state)


if __name__ == "__main__":
    main()
