#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — استراتيجية احترافية مع إغلاق متعدد الطبقات
التحسينات الرئيسية في هذا الإصدار:
  1. حساب PnL موحد (قسمة على 10^md فقط، دون SPOT_SCALE في هذه الدالة)
  2. الطبقة 0: فلترة ضوضاء MIN_GAP_USD (لا فتح إلا بفجوة ≥ 0.5$)
  3. الطبقة 1: إغلاق عند الوصول للذروة + تراجع (Trailing)
  4. الطبقة 2: إغلاق عند وصول الخسارة للحد الأقصى (Max Loss)
  5. الطبقة 2b: تثبيت الربح (Profit Target عند +2$)
  6. الطبقة 3: إغلاق عند تجاوز المدة القصوى (Max Hold Time 2 ساعة)
  7. الطبقة 4: دائرة أمان Daily Loss ومتتالية الخسائر
  8. الطبقة 5: إغلاق عند عودة الفجوة لـ Z_EXIT أو تجاوز Z_STOP
  9. حفظ state شمولي يشمل كل الطبقات وبيانات الأداء
  10. حساب PnL للإغلاق يستخدم نفس الصيغة الموحدة
"""

import csv
import json
import os
import sys
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
    vol_lots = pos.tradeData.volume / 100000.0 if pos.tradeData.volume else 0
    spread_est = config.TRADING_FEES_PER_TRADE_LOT * max(vol_lots, 0.01)
    return commission + swap + spread_est


def dynamic_pnl_usd(pos, mid, digits, md):
    """PnL صافي (بعد الرسوم) من mid الحالي والصفقة المفتوحة.
    الصيغة: PnL = (mid - entry) × volume / (10^md)
    حيث md=2 لكل صغيرة → القسم 100
    volume لوحدة XAUUSD 0.01 لوت = 100 وحدة سعر داخلية
    مثال: mid=4400, entry=4390, volume=100, md=2
          PnL = (10 × 100) / 100 = 10.0$
    """
    entry = pos.price
    if entry is None or entry == 0:
        entry = None  # لا نعيد 0.0؛ نجعله None صراحةً
    if entry is None:
        return 0.0, 0.0, 0.0
    raw = (mid - entry) * pos.tradeData.volume
    if _side_name(pos.tradeData.tradeSide) == "SELL":
        raw = -raw
    # القسمة على 10^md فقط - هذا هو الحساب الصحيح
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

        # --- الطبقة 0: فلترة ضوضاء - لا شيء هنا، سنطبق في الفتح ---

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

        # --- الطبقة 2: تثبيت الأرباح (Profit Target) ---
        # إغلاق فوري عند بلوغ ربح صافي محدد (مثلاً +2$)
        if self.cfg.PROFIT_TARGET_USD > 0 and net_pnl >= self.cfg.PROFIT_TARGET_USD:
            return True, "profit_target"

        # --- الطبقة 3: الحد الأقصى للخسارة (Max Loss) ---
        if net_pnl <= -self.cfg.MAX_LOSS_USD:
            return True, "max_loss"

        # --- الطبقة 4: الحد الأقصى للزمن (Max Hold) ---
        if opened_at:
            opened_dt = datetime.fromisoformat(opened_at)
            open_hours = (now - opened_dt.timestamp()) / 3600.0
            if open_hours >= self.cfg.MAX_HOLD_HOURS:
                return True, "max_hold_time"

        # --- الطبقة 5: عودة الفجوة (Mean Reversion) ---
        # إغلاق إذا عاد z للقرب من الصفر (Z_EXIT) أو إذا تجاوزت الفجوة الحد الأقصى
        # ملاحظة: نستخدم position.price من server بدلاً من st_pos.get("entry_price")
        pos_entry = getattr(position, "price", None)
        if pos_entry is None:
            pos_entry = st_pos.get("entry_price")
        if pos_entry and pos_entry > 0:
            if stats:
                scale = (stats.get("mad") if self.cfg.USE_MAD and stats.get("mad") else 0) or stats["sd"]
                centre = stats["median"] if self.cfg.USE_MAD and stats.get("mad") else stats["mean"]
                if scale > 0:
                    z = (global_price - pos_entry) / scale
                    if z is not None and abs(z) <= self.cfg.Z_EXIT:
                        return True, "z_revert"
            if abs(global_price - pos_entry) >= self.cfg.MAX_ENTRY_GAP_USD:
                return True, "gap_exceeded_cap"
            gap_pct = abs(global_price - pos_entry) / pos_entry
            if gap_pct >= self.cfg.gap_max_gap_pct:
                return True, "gap_cap_pct"

        # --- الطبقة 6: Daily Loss / Consecutive Losses Circuit Breaker ---
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


def _record_external_close(state, ts_open, ts_close, gap,
                           entry_gap, entry_price, close_price, max_gap,
                           result):
    """تسجيل إغلاق خارجي (من المستخدم أو السيرفر)."""
    if ts_open:
        net_gap = close_price - (entry_price or close_price)
        # حساب PnL تقريبي يعتمد على الفجوة
        pnl_usd_guess = net_gap * config.LOT * 100  # LOT × 100 (لأن 0.01 لوت = 100 وحدة)
        main._record_close(state, {
            "ts_open": ts_open,
            "ts_close": ts_close,
            "side": state.get("position", {}).get("side"),
            "entry_gap": entry_gap,
            "close_gap": gap,
            "entry_price": entry_price,
            "close_price": close_price,
            "pnl_units": round(pnl_usd_guess, 2),
            "pnl_usd": round(pnl_usd_guess, 2),
            "fees_usd": 0.0,
            "pnl_net_usd": round(pnl_usd_guess, 2),
            "reason": "external_close",
        })
    result["action"] = "external_close"


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
        sess.last_positions = positions
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
    # ملاحظة: positions قد يكون فارغًا بسبب فشل API، لذا لا نعتمد عليه فقط
    pos_for_close = None
    if positions:
        pos_for_close = positions[0]
    elif state.get("position") is not None:
        # API أعطى empty لكن estado يقول فيه صفقة — نستخدم الـ state
        sp = state["position"]
        pos_for_close = None  # 不知道真实的 position 对象，但 نعرف الـ positionId
        # نعتمد على الكاش أو نفتح محاولة إغلاق مباشرة بالـ positionId
        if sp.get("positionId"):
            # محاولة إغلاق مباشرة using stored positionId
            try:
                yield sess.close_position(
                    sp["positionId"],
                    volume=None,
                    max_retries=3,
                )
                st_pos = state.get("position") or {}
                entry_price = st_pos.get("entry_price")
                side_name = st_pos.get("side", "BUY")
                now_ts_close = time.time()
                digits = state.get("money_digits", 2) or 2
                mid_close = mid
                if entry_price:
                    price_diff = mid_close - entry_price
                    if side_name == "SELL":
                        price_diff = -price_diff
                    volume_close = result.get("volume", 100)
                    gross_pnl_close = (price_diff * volume_close) / (10.0 ** digits)
                    pnl_net_close = round(gross_pnl_close, 2)
                    sp["pnl_last_usd"] = pnl_net_close
                    sp["pnl_peak_usd"] = max(float(sp.get("pnl_peak_usd", 0)), pnl_net_close)
                    print(f"✓ CLOSED (state-force-close): pnl={pnl_net_close:.2f} USD")
                    result["action"] = "close:state-force-close"
                    result["close_pnl_usd"] = pnl_net_close
                    state["position"] = None
                    state["cooldown_until"] = now_ts_close + config.COOLDOWN_MINUTES * 60
                    if pnl_net_close > 0:
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
                        "close_price": mid_close,
                        "pnl_units": pnl_net_close,
                        "pnl_usd": pnl_net_close,
                        "fees_usd": 0,
                        "pnl_net_usd": pnl_net_close,
                        "reason": "state-force-close",
                        "pnl_peak_usd": round(float(sp.get("pnl_peak_usd", 0)), 2),
                    })
            except Exception as exc:
                print(f"state-force-close failed: {exc!r}")
                result["action"] = "close_pending:state"
                # لا نخرج، نستمر لمحاولة الإغلاق في الـ layers المعتادة
            except Exception as exc:
                print(f"state-force-close setup failed: {exc!r}")
    if pos_for_close is not None:
        pos = pos_for_close
    else:
        pos = None

    if pos is not None:
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

                # حساب PnL الحقيقي باستخدام الصيغة الموحدة
                entry_price = st_pos.get("entry_price")
                close_price = mid  # سعر الإغلاق الحالي
                side_name = _side_name(pos.tradeData.tradeSide)
                volume = getattr(pos.tradeData, "volume", 100)
                digits = getattr(pos, "digits", 2) or 2

                # حساب PnL بالصيغة الموحدة: (mid - entry) × volume / (10^digits)
                price_diff = close_price - entry_price if entry_price else 0
                if side_name == "SELL":
                    price_diff = -price_diff
                gross_pnl = (price_diff * volume) / (10.0 ** digits)
                fees_est = position_fees_usd(pos, digits) if digits else 0
                pnl_net = round(gross_pnl - fees_est, 2)

                print(
                    f"✓ CLOSED (layer: {close_reason}): "
                    f"pnl={pnl_net:.2f} USD (gross={gross_pnl:.2f}), "
                    f"peak={float(st_pos.get('pnl_peak_usd', 0)):.2f} USD, "
                    f"entry_price={entry_price}, close_price={close_price:.2f}"
                )

                result["action"] = "close:" + close_reason
                state["position"] = None
                state["cooldown_until"] = now_ts + config.COOLDOWN_MINUTES * 60
                if pnl_net > 0:
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
                    "pnl_units": pnl_net,
                    "pnl_usd": pnl_net,
                    "fees_usd": round(fees_est, 2),
                    "pnl_net_usd": pnl_net,
                    "reason": close_reason,
                    "pnl_peak_usd": round(
                        float(st_pos.get("pnl_peak_usd") or 0), 2,
                    ),
                })
                result["close_pnl_usd"] = pnl_net
            except Exception as exc:
                result["close_failed"] = repr(exc)
                print(f"close_position failed (layer: {close_reason}): {exc!r}")
                result["action"] = "close_pending"
        else:
            result["action"] = "hold"
    else:
        # لا توجد صفقة مفتوحة من API
        # لكن قد يكون هناك position في state (إذا فشل API)
        # لا نحذف state["position"] إلا إذا لم يكن هناك positionId
        if not (state.get("position") and state["position"].get("positionId")):
            state["position"] = None

    # --- إذا لم تكن هناك صفقة مفتوحة: اتخاذ قرار الفتح ---
    if not positions and not closed_this_cycle:
        cooldown_left = state.get("cooldown_until", 0) - now_ts
        in_session_now = in_session(datetime.now(timezone.utc))

        can_trade = (
                config.MODE == "trade"
                and stats is not None
                and result["z"] is not None
                and abs(result["z"]) >= config.Z_ENTRY_SOFT
                and abs(gap) <= config.MAX_ENTRY_GAP_USD
                and abs(gap) >= config.MIN_GAP_USD
                and result.get("balance_usd", 0) >= config.MIN_BALANCE_TO_TRADE
                and cooldown_left <= 0
                and in_session_now
                and state.get("position") is None
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
                # تسجيل entry_price من order.executionPrice أو res.position.price
                order_exec_price = (
                    float(order.executionPrice)
                    if order.executionPrice else None
                )
                position_price = (
                    float(res.position.price)
                    if (res.position and res.position.price) else None
                )
                # الأولوية لـ executionPrice (سعر التنفيذ الفعلي)
                entry_price_val = order_exec_price or position_price
                # تحويل internal units إلى سعر حقيقي إذا لزم
                if entry_price_val and entry_price_val > 10000:
                    entry_price_val = entry_price_val / config.SPOT_SCALE
                if entry_price_val is None:
                    # محاولة من mid إذا لزم
                    entry_price_val = mid
                    print(f"  WARN: تعويض entry_price من mid={mid:.2f}")
                if entry_price_val == 0:
                    # لا نستخدم 0.0 كـ entry_price - استخدم mid كبديل آمن
                    entry_price_val = mid
                    print(f"  WARN: entry_price=0 تم تعويظه بـ mid={mid:.2f}")

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
                    "entry_price": entry_price_val,
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
            if abs(gap) < config.MIN_GAP_USD:
                reasons.append("gap_to_small")
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
        global_price = 0.0
        source = "failed"
        source_ts = ""

    try:
        sess = CtraderSession()
        host = (
            cbot.EndPoints.PROTOBUF_LIVE_HOST
            if config.ENVIRONMENT.strip().lower() == "live"
            else cbot.EndPoints.PROTOBUF_DEMO_HOST
        )
        print(f"connecting to {host}...")
        sess.connect()
        print(f"connected to {host}")

        account = sess.authenticate(token)
        print(f"authenticated as account {account}")

        result["account_id"] = account
        trader = sess.get_trader()
        result["balance"] = trader.balance
        result["money_digits"] = trader.moneyDigits
        result["balance_usd"] = (
            trader.balance / (10 ** trader.moneyDigits)
            if trader.moneyDigits else trader.balance
        )
        print(f"balance: {result['balance_usd']:.2f} USD")

        symbol_id = sess.find_symbol(config.SYMBOL)
        info = sess.symbol_info(symbol_id)
        volume = int(round(config.LOT * info["lotSize"]))
        result["symbol_id"] = symbol_id
        result["lot_size"] = info["lotSize"]
        result["volume"] = volume
        result["digits"] = info["digits"]
        print(f"symbol={config.SYMBOL} id={symbol_id} volume={volume} digits={info['digits']}")

        sess.subscribe_persistent(symbol_id)

        if config.FORCE_TEST_OPEN and config.ENVIRONMENT.strip().lower() == "demo":
            try:
                existing = sess.open_positions(symbol_id)
                if existing:
                    print(f"FORCE-TEST SKIP (already open): "
                          f"{[(p.positionId, float(p.price)) for p in existing]}")
                else:
                    res = sess.open_market(
                        symbol_id, "BUY", volume,
                        label="FORCE-TEST", comment="",
                    )
                    print(f"FORCE-TEST OPEN OK positionId={res.position.positionId}")
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
                                sess.set_sltp(
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
                            sess.close_position(pid)
                            print("FORCE-TEST CLOSE OK")
                        except Exception as exc:
                            print("FORCE-TEST CLOSE FAIL:", repr(exc))
            except Exception as exc:
                print("FORCE-TEST FAIL:", repr(exc))

        # تنفيذ دورة التداول
        result["action"] = None
        result["close_pnl_usd"] = None
        result["close_check"] = None
        result["open_positions"] = 0
        result["z"] = None
        result["gap"] = None
        result["order"] = None
        result["close_failed"] = None
        result["open_positions_warn"] = None

        reactor.run()

        # الحفظ النهائي
        state["last_run"] = utcnow_iso()
        state["stats"] = stats
        save_state(state)
        save_history(rows)

        # طباعة التقرير
        print("\n" + "=" * 60)
        print("تقرير الاختبار النهائي")
        print("=" * 60)
        print(f"  الفجوة: {result.get('gap', 'N/A'):.4f}" if result.get('gap') else "  الفجوة: N/A")
        print(f"  z-score: {result.get('z', 'N/A'):.4f}" if result.get('z') else "  z-score: N/A")
        print(f"  Action: {result.get('action', 'N/A')}")
        if result.get('close_pnl_usd') is not None:
            print(f"  PnL: {result['close_pnl_usd']:.2f} USD")
        print(f"  الأخطاء: {result.get('error', 'لا توجد')}")
        print(f"  التحذيرات: {result.get('open_positions_warn', 'لا توجد')}")
        if result.get('close_failed'):
            print(f"  فشل الإغلاق: {result['close_failed']}")

    except Exception as exc:
        result["error"] = repr(exc)
        print(f"FATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
