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
  11. إصلاح جذري: منع تعدد الصفقات، إغلاق عند فشل API، تتبع الربح الصحيح
  12. [2026-09-14] إعادة بناء جذرية للخوارزمية: إشارة الدخول أصبحت
      انحراف سعر المنصة (mid) عن وسطه المتداول (z-score على mid) بدلاً من
      الفجوة (mid - global_price) بعدما أظهر التحليل أن الفجوة لا ترتد
      للصفر فعلياً (+0.04 فقط بعد الدخول). global_price يبقى للرصد
      ولحارس البيانات الشاذة فقط.
"""

import csv
import json
import os
import sys
import time
import types
from datetime import datetime, timezone

import config
import gold_price
import cbot
from cbot import CtraderSession
from ctrader_open_api import Auth
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import deferLater

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
    """إحصاءات على سعر المنصة (platform/mid) نفسه — وليس الفجوة.

    تغيير جوهري (2026-09-14): تحليل البيانات أظهر أن الفجوة
    (mid - global price من مصدر خارجي غير متزامن) لا ترتد إلى الصفر
    فعلياً (متوسط تغير السعر بعد فجوة<-1.5 = +0.04 فقط). لذلك أصبحت
    إشارة الدخول تعتمد على انحراف سعر المنصة عن وسطه المتداول (z-score
    على mid) بدلاً من حجم الفجوة. الفجوة تبقى فقط للرصد.
    """
    valid = [
        r for r in rows
        if config.MIN_PLATFORM_PRICE <= r["platform"] <= config.MAX_PLATFORM_PRICE
    ]
    valid = valid[-config.ROLLING_WINDOW:]
    if verbose:
        print(f"stats: valid samples in window = {len(valid)}")
    if len(valid) < config.MIN_SAMPLES:
        return None
    gaps = sorted(r["platform"] for r in valid)
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


def in_quality_session(dt):
    """فلترة جودة الجلسة: نحظر نافذة ضعيفة معروفة (إغلاق لندن والانتقال).

    تحليل الصفقات الحقيقية مع البحث:
      - 16:00–22:00 UTC: نسبة فوز 56% ومعظم الخسائر (إغلاق لندن، 21-22 تسوية).
      - 22:00–05:00 UTC: نسبة فوز 80% (سيولة تنظيمية آسيوية).
      - 09:00–16:00 UTC: نسبة فوز 100% (ذروة لندن + تداخل NY بالسيولة).
    لذلك نمنع الفتح داخل نافذة [16:00–22:00) افتراضياً.
    """
    if not config.SESSION_BLOCK_ON:
        return True
    hour = dt.hour + dt.minute / 60.0
    start = config.SESSION_BLOCK_START_HOUR
    end = config.SESSION_BLOCK_END_HOUR
    if start <= end:
        return not (start <= hour < end)
    # نافذة ملتفة عبر منتصف الليل (مثال نادر)
    return not (hour >= start or hour < end)


def yahoo_momentum(rows, max_rows=None):
    """زخم ياهو GC=F (العقود الآجلة — القائد الفعلي).

    البحث الحي (2026-09-15): ياهو GC=F يحدث سعره كل 1-3 ثوانٍ
    بـ 28 تغيراً في 60 ثانية، بينما gold-api يحدث مرة كل 30 ثانية
    بتغير واحد فقط. ياهو هو السوق الأكثر سيولة عالمياً للذهب.

    البنية: Yahoo(عقود آجلة 4343$) → gold-api(سبوت 4306$) →
    المنصة(cTrader XAUUSD 4306$). الفرق البنوي ~37$ (لفائدة+تكلفة
    حمل) يتغير ببطء.

    الاستراتيجية: نتداول باتجاه زخم ياهو (القائد) متوقعين لحاق
    المنصة. القيمة = Δglobal (الآن = Yahoo) خلال آخر N صفوف.
    """
    if max_rows is None:
        max_rows = config.MOMENTUM_WINDOW_ROWS
    try:
        valid = [r for r in rows if isinstance(r.get("global"), (int, float))]
        valid = valid[-max_rows:]
        if len(valid) < 2:
            return 0.0
        return valid[-1]["global"] - valid[0]["global"]
    except Exception:
        return 0.0


def platform_momentum(rows, max_rows=None):
    """زخم سعر المنصة (mid) — مؤشر تأكيدollower. القيمة الإيجابية = صاعد."""
    if max_rows is None:
        max_rows = config.MOMENTUM_WINDOW_ROWS
    try:
        valid = [r for r in rows if isinstance(r.get("platform"), (int, float))]
        valid = valid[-max_rows:]
        if len(valid) < 2:
            return 0.0
        return valid[-1]["platform"] - valid[0]["platform"]
    except Exception:
        return 0.0


def platform_anomaly_usd(rows, span_rows=20):
    """قفزة غير صحّية في سعر المنصة (خلل شريط/سيولة شاذة) — بالدولار.

    مفهوم 2026-09-14: لما لم تعد الفجوة إشارة دخول (الزخم هو الإشارة)،
    حارس الشذوذ يجب ألا يعتمد على |gap| إطلاقاً — الفجوة تختلف جذرياً
    حسب المصدر (السبوت gold-api≈4306 مقابل GC=F ياهو≈4338: فرق بنيوي
    ~32$). لو سقط gold-api ورجعنا لـ Yahoo ستكون |gap|≈32 دائماً وكان
    سيغلق كل صفقة خطأً. الحارس الصحيح = مقدار تحرك mid خلال ثوانٍ
    (≈span_rows × 4s): قفزات غير طبيعية تُرصد مباشرة من سعر المنصة.
    """
    try:
        valid = [r for r in rows if isinstance(r.get("platform"), (int, float))]
        valid = valid[-span_rows:]
        if len(valid) < 2:
            return 0.0
        return abs(valid[-1]["platform"] - valid[0]["platform"])
    except Exception:
        return 0.0


def trend_slope(rows, max_rows=None):
    """انحدار سعر المنصة (platform/mid) بالدولار/دقيقة خلال نافذة حديثة.

    أُعيدت صياغته (2026-09-14): كان يقيس انحدار سعر المرجع الخارجي
    (global) ويمنع الدخول حين aligns مع الفجوة. الآن الإشارة على سعر
    المنصة نفسه، فالمنع يجب أن يقاس على نفس السلسلة التي نتداولها.

    القيمة الموجبة = السعر صاعد، السالبة = هابط. تُستعمل مع
    TREND_MAX_SLOPE_USD لمنع الدخول ضد اتجاه قوي.
    """
    if not config.TREND_ON:
        return 0.0
    if max_rows is None:
        max_rows = config.TREND_WINDOW_ROWS
    try:
        valid = [r for r in rows if isinstance(r.get("platform"), (int, float))]
        valid = valid[-max_rows:]
        if len(valid) < 2:
            return 0.0
        t0 = datetime.fromisoformat(valid[0]["ts"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(valid[-1]["ts"].replace("Z", "+00:00"))
        dt = (t1 - t0).total_seconds() / 60.0
        if dt <= 0:
            return 0.0
        return (valid[-1]["platform"] - valid[0]["platform"]) / dt
    except Exception:
        return 0.0


# ===== إنسانية التنفيذ =====
_HUMAN_WORDS_A = ("clear", "trade", "gold", "steady", "manual", "afx",
                  "alpha", "delta", "prime", "north", "silver", "cartel",
                  "keeper", "bridge", "market", "haven")
_HUMAN_WORDS_B = ("one", "two", "five", "main", "quick", "echo", "nova",
                  "sun", "moon", "peak", "core", "swift", "round", "solid")
_HUMAN_WORDS_B = ("one", "two", "five", "main", "quick", "echo", "nova",
                  "sun", "moon", "peak", "core", "swift", "round", "solid")


def _human_label():
    """اسم صفقة مقروء يشبه تعليق المتداول اليدوي — ليس رموزاً عشوائية.

    القاعدة 3: لا يظهر في label/comment أي شيء يدل على البوت أو على
    منطق الفجوة/القائد-التابع. عينة: "gold steady" / "afx one".
    """
    import random as _r
    w = _r.choice(_HUMAN_WORDS_A) + " " + _r.choice(_HUMAN_WORDS_B)
    return w


def _jitter_usd(base, max_jit):
    """يرجع base مضافاً/منقوصاً قليلاً ضمن ±max_jit — تشتت بشري.

    القاعدة 1: لا أوامر SL/TP متطابقة حرفياً كل مرة، بل مسافات
    قريبة مع تشتت طبيعي (ضمن حدود أمان).
    """
    import random as _r
    if not config.HUMANIZE_ON or max_jit <= 0:
        return base
    return base + _r.uniform(-max_jit, max_jit)


def _human_reaction():
    """تأخير بشري قبل إرسال الأمر (محاكاة تفكير/تنفيذ يدوي).

    القاعدة 2: تأخير عشوائي ضمن نطاق إعدادات HUMAN_REACTION_SEC.
    يرجع 0 إذا كانت الإنسانية معطلة.
    """
    import random as _r
    if not config.HUMANIZE_ON:
        return 0.0
    return _r.uniform(config.HUMAN_REACTION_SEC_MIN,
                      config.HUMAN_REACTION_SEC_MAX)


def _skip_signal():
    """يُفوّت الإنسان أحياناً إشارة صالحة. يرجع True للتفويت.

    القاعدة 4: احتمال HUMAN_SKIP_SIGNAL_PROB لتخطي دخول — يبعد
    "التقاط كل شيء" الآلي عن البصمة البوتية.
    """
    import random as _r
    if not config.HUMANIZE_ON:
        return False
    return _r.random() < config.HUMAN_SKIP_SIGNAL_PROB


def _jittered_volume(base_volume):
    """حجم عشوائي بسيط حول الأساس (±HUMAN_VOLUME_JITTER_FRAC).

    القاعدة 1: غير ثابت دائماً منذ البداية؛ بروكر يرى أحجاماً متنوعة.
    يُكمَّل عند الوسيط إلى أقرب مضاعف لخطوة الحجم الصالحة
    (VOLUME_STEP_UNITS) حتى لا يرُفض الأمر بـ TRADING_BAD_VOLUME
    (حجم داخل درجة الوسيط). عند اللوت الأساسي 0.01 (=100 وحدة) يبقى
    100 كما هو لأن أي قيوم أخرى بلا مضاعف خطوة.
    """
    import random as _r
    if not config.HUMANIZE_ON or base_volume <= 0:
        return base_volume
    jit = _r.uniform(-config.HUMAN_VOLUME_JITTER_FRAC,
                     config.HUMAN_VOLUME_JITTER_FRAC)
    step = max(1, int(getattr(config, "VOLUME_STEP_UNITS", 100) or 1))
    raw = base_volume * (1 + jit)
    snapped = int(round(raw / step)) * step
    return max(step, snapped)


def _poll_jitter():
    """تشتت صغير على فترة الجرد — لا دورة آلية ثابتة النبض.

    القاعدة 5: GLOBAL_POLL_SEC ± HUMAN_POLL_JITTER_SEC.
    """
    import random as _r
    if not config.HUMANIZE_ON:
        return config.GLOBAL_POLL_SEC
    jit = _r.uniform(-config.HUMAN_POLL_JITTER_SEC,
                     config.HUMAN_POLL_JITTER_SEC)
    return max(1.0, config.GLOBAL_POLL_SEC + jit)


def _stable_jitter(seed, span_frac):
    """تشتت ثابت لكل صفقة في المدى [-span_frac, +span_frac].

    يُشتق من معرّف الصفقة (positionId) فيبقى ثابتاً طول عمر الصفقة،
    فلا يتردد قرار الإغلاق بين دورة وأخرى. القاعدة 1 (لا عتبات
    أرباح متطابقة دقیقاً كل صفقة).
    """
    if not config.HUMANIZE_ON or not seed:
        return 0.0
    try:
        h = abs(hash(str(seed))) % 10000
        return ((h / 10000.0) * 2.0 - 1.0) * span_frac
    except Exception:
        return 0.0


def _side_name(trade_side):
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as Models
    for name, num in Models.ProtoOATradeSide.DESCRIPTOR.values_by_name.items():
        if num == trade_side:
            return name
    return str(trade_side)


def _detected_spread_usd(result=None):
    """يرجع السبريد الحي (bid→ask) من آخر دورة، أو 0 إن غاب.

    القاعدة المرجعية 2026-09-15: التكلفة الفعلية للصفقة تشمل السبريد
    الحي (المقيس من cTrader bid/ask) + العمولة الفعلية + السواب. لا
    نستخدم تقديراً ثابتاً للسبريد بعد الآن — ونقرأ القياس من أي مصدر
    متاح (spread_usd ثم _spread_live) دون عودة مبكرة بـ 0 تُفقد المصدر
    الثاني (كانت تُسقط التقدير الثابت 0.40 على check_close المارر عبر
    _spread_live — فأُصبح التريلنج يتطلب ربحاً أعلى بكثير).
    """
    if result is not None:
        for key in ("spread_usd", "_spread_live"):
            try:
                v = float(result.get(key) or 0.0)
            except (TypeError, ValueError):
                continue
            if v > 0:
                return v
    return 0.0


def _spread_from_state_res(state=None):
    """قراءة السبريد الحي من state (الصق من آخر دورة تقييم)."""
    if state is None:
        return 0.0
    try:
        return float(state.get("_last_spread_usd") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _commission_usd(pos, md=None, state=None):
    """عمولة الصفقة بالدولار.

    الأولوية: العمولة الفعلية من كائن الصفقة (pos.commission) إن وُجدت
    وقابلة للاستخدام؛ وإلا معايرة من متوسط العمولة الفعلية المسجلة في
    الصفقات المغلقة (state.perf.measured_commission_usd)؛ وإلا تقدير
    الثابت TRADING_FEES_PER_TRADE_LOT لكل لوت.
    """
    commission = 0.0
    try:
        commission = float(getattr(pos, "commission", None) or 0.0)
        if md and commission:
            commission = commission / (10.0 ** md)
    except (TypeError, ValueError):
        commission = 0.0
    if commission and commission > 0:
        return commission
    # معايرة ذاتية من الصفقات المغلقة الفعلية
    perf = {}
    if state is not None:
        perf = state.get("perf") or {}
    cal = float(perf.get("measured_commission_usd") or 0.0)
    if cal and cal > 0:
        return cal
    vol_lots = float(config.LOT) if getattr(config, "LOT", None) else 0.01
    return config.TRADING_FEES_PER_TRADE_LOT * max(vol_lots, 0.01)


def position_fees_usd(pos, md, result=None, state=None):
    """تكلفة الصفقة الإجمالية (عمولة + سواب + السبريد الحي المقيس).

    2026-09-15: لم نعد نقدّر السبريد ثابتاً — نقيسها حياً من bid/ask
    عبر result["spread_usd"].
    """
    commission = _commission_usd(pos, md, state=state)
    swap = getattr(pos, "swap", None) or 0
    if not swap:
        try:
            swap = float(getattr(pos, "swap", 0) or 0)
        except (TypeError, ValueError):
            swap = 0.0
    if md:
        swap = swap / (10.0 ** md)
    else:
        try:
            swap = float(swap)
        except (TypeError, ValueError):
            swap = 0.0
    spread_est = _detected_spread_usd(result)
    if spread_est <= 0:
        # fallback: تقدير متحفظ (عرض نموذجي للذهب ~0.35$) إن غاب القياس
        spread_est = config.SPREAD_GUARD_USD * 0.5
    return commission + swap + spread_est


def dynamic_pnl_usd(pos, mid, digits, md, st_pos=None, result=None,
                    state=None):
    """PnL صافي (بعد الرسوم) من mid الحالي والصفقة المفتوحة.
    الصيغة: PnL = (mid - entry) × volume / (10^md)
    حيث md=2 لكل صغيرة → القسم 100
    volume لوحدة XAUUSD 0.01 لوت = 100 وحدة سعر داخلية
    مثال: mid=4400, entry=4390, volume=100, md=2
          PnL = (10 × 100) / 100 = 10.0$
    """
    entry = None
    # نفضل entry_price المخزن في state (حقيقي، مقسوم على SPOT_SCALE)
    if st_pos is not None:
        try:
            entry = float(st_pos.get("entry_price"))
        except (TypeError, ValueError):
            entry = None
    if entry is None:
        entry = getattr(pos, "price", None)
    if entry is None or entry == 0:
        return 0.0, 0.0, 0.0
    # إن كان سعراً خاماً مضروباً بـ 100000 نجعل الحقيقي
    if abs(entry) > 10000:
        entry = entry / config.SPOT_SCALE
    raw = (mid - entry) * pos.tradeData.volume
    if _side_name(pos.tradeData.tradeSide) == "SELL":
        raw = -raw
    # القسمة على 10^md فقط - هذا هو الحساب الصحيح
    gross = raw / (10.0 ** (md or 2))
    fees = position_fees_usd(pos, md, result=result, state=state)
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
        # إعادة ضبط يومي: إذا كان آخر تحديث في يوم مختلف، نصفر العدادات
        last_updated = perf.get("last_updated")
        if last_updated:
            try:
                last_date = datetime.fromisoformat(last_updated).date()
                today = datetime.utcnow().date()
                if last_date != today:
                    self.daily_pnl = 0.0
                    self.trade_count_today = 0
                    self.consecutive_losses = 0
                    # نكتب النتائج فوراً في state حتى يُحفظ بأول
                    # save_state دوري دون انتظار صفقة/إغلاق
                    state["perf"] = {
                        "running_daily_pnl": 0.0,
                        "consecutive_losses": 0,
                        "trades_today": 0,
                        "last_updated": utcnow_iso(),
                    }
            except (ValueError, TypeError):
                pass

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
        if self.trade_count_today >= self.cfg.MAX_TRADES_PER_DAY:
            return False
        return True

    def record_loss(self, pnl_usd=0.0):
        """تسجيل خسارة وتحديث العدادات بقيمة حقيقية بالدولار."""
        self.consecutive_losses += 1
        self.trade_count_today += 1
        self.daily_pnl -= abs(pnl_usd) if pnl_usd else 1.0

    def record_win(self, pnl_usd=0.0):
        """تسجيل ربح وإعادة تعيين عداد الخسائر بقيمة حقيقية بالدولار."""
        self.consecutive_losses = 0
        self.trade_count_today += 1
        self.daily_pnl += pnl_usd if pnl_usd else 1.0

    def check_close(self, position, mid, global_price, stats,
                    st_pos, now, money_digits):
        """فحص جميع طبقات الإغلاق واقتراح الإغلاق إن لزم.

        يُرجع (should_close: bool, reason: str or None)
        """
        side_name = _side_name(position.tradeData.tradeSide)
        digits = getattr(position, "digits", 2) or 2
        # التكلفة الفعلية: عمولة (فعلية/معايرة) + سواب + السبريد الحي
        # المقيس من cTrader bid/ask (آخر دورة).
        net_pnl, gross_pnl, fees = dynamic_pnl_usd(
            position, mid, digits, money_digits, st_pos,
            result={"_spread_live": _spread_from_state_res(self.state)},
            state=self.state,
        )
        entry_gap = st_pos.get("entry_gap")
        entry_price = st_pos.get("entry_price")
        opened_at = st_pos.get("opened_at")

        # تتبع الأرباح: أعلى صافي ربح بلغته الصفقة منذ فتحها. تبدأ من
        # 0.0 ولا تنزل تحت الصفر (القمة الحقيقية، لا القيمة الحالية
        # السالبة) حتى يعمل التريلنج صحيحاً عند وصول الربح لدرجة التفعيل.
        _stored_peak = st_pos.get("pnl_peak_usd")
        peak = float(_stored_peak) if _stored_peak is not None else 0.0
        peak = max(peak, 0.0)
        peak = max(peak, net_pnl)

        # إنسانية: عتبات الربح/التريلنج تختلف قليلاً من صفقة لأخرى (ثابتة
        # لكل صفقة) حتى لا تبدو الأرباح المثبّتة متطابقة بالبنس دائماً.
        # max_loss يبقى صارماً بلا تشتت (حد أمان لا يُمَس).
        _seed = getattr(position, "positionId", None)
        _bias = _stable_jitter(_seed, 0.15)
        prof_target = self.cfg.PROFIT_TARGET_USD * (1.0 + _bias)
        trail_arm = self.cfg.TRAILING_ARM_USD * (1.0 + _bias)
        trail_back = self.cfg.TRAILING_BACK_USD * (1.0 + _bias)

        # --- الطبقة 0: فلترة ضوضاء - لا شيء هنا، سنطبق في الفتح ---

        # --- الطبقة 1: إغلاق بالربح (Trailing) ---
        # تفعيل الترهل: profit >= TRAILING_ARM_USD
        trailing_armed = (
            self.cfg.TRAILING_ARM_USD > 0
            and peak >= trail_arm
            and self.cfg.TRAILING_BACK_USD > 0
        )
        trailing_hit = trailing_armed and (peak - net_pnl) >= trail_back
        # لا نغلق بالتريلنج على خسارة: التريلنج يحمي الربح، لا يصنع خسائر.
        # (الخسارة الصغيرة تُترك حتى طبقة max_loss أو الستوب الفعلي)
        if trailing_hit:
            if net_pnl >= 0:
                return True, "trailing"
            # net_pnl < 0: نُبقي الصفقة — قد تكون عائدة نحو الربح
            st_pos["pnl_peak_usd"] = round(peak, 2)

        # --- الطبقة 2: تثبيت الأرباح (Profit Target) ---
        # إغلاق فوري عند بلوغ ربح صافي محدد (مثلاً +2$)
        if prof_target > 0 and net_pnl >= prof_target:
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

        # --- الطبقة 4ب: صفقة بلا وقوف سيرفر (SL/TP) تُغلق فوراً ---
        # القاعدة الجذرية 2026-09-16: لا يجوز أن تبقى أي صفقة مفتوحة دون
        # SL/TP مقبول على السيرفر — لو توقف البوت لساعات بقيت معلقة.
        # أي صفقة من دون الحماية تُغلق قسراً فور تجاوز الدقائق الأولى.
        if opened_at and not st_pos.get("sltp_set"):
            opened_dt = datetime.fromisoformat(opened_at)
            if now - opened_dt.timestamp() >= 120:
                return True, "no_broker_stops"

        # --- (الطبقة 5 أُزيلت 2026-09-16) عودة السعر لمركز قناته ---
        # بيانات 185 صفقة: z_revert كان أول نقطة اكتمال للّحاق (مركز قناة
        # المنصة) — أي بداية الحركة الصحيحة لا نهايتها؛ 44 صفقة متوسطة
        # +0.48$ فقط = أرباح مبتورة. نظام الإغلاق الجديد يعتمد على ستوب
        # سيرفر 2.0 + TP سيرفر (1.40+) + تريلنج فوق الهدف لا إغلاق مبكر.
        # حارس أمان شاذ: قفزة تلقائية من إشارة الزخم (تُملأ على النحو
        # التالي live/state). لو كانت حركة mid خلال ~80 ثانية غير معقولة
        # فهذا خلل شريط — نغلق لحماية الصفقة.
        jump = abs(self.state.get("_anomaly_jump", 0.0) or 0.0)
        if jump >= self.cfg.PRICE_JUMP_ANOMALY_USD:
            return True, "price_anomaly"

        # --- الطبقة 6: Daily Loss / Consecutive Losses Circuit Breaker ---
        # لا تطبق هنا لأنها تؤثر على الفتح وليس الإغلاق

        st_pos["pnl_peak_usd"] = round(peak, 2)
        st_pos["pnl_last_usd"] = round(net_pnl, 2)
        track = st_pos.setdefault("pnl_track", [])
        track.append(round(net_pnl, 2))
        if len(track) > 120:
            del track[:-120]

        return False, None

    def record_close(self, state, win, pnl_usd=0.0):
        """تسجيل نتائج الصفقة المغلقة بالربح الفعلي."""
        if win:
            self.record_win(pnl_usd)
        else:
            self.record_loss(pnl_usd)
        self.save_perf_to_state(state)


# ============================================================================
# trade logic
# ============================================================================


def _record_close(state, rec):
    trades = state.setdefault("closed_trades", [])
    trades.append(rec)
    if len(trades) > config.MAX_CLOSED_TRADES:
        state["closed_trades"] = trades[-config.MAX_CLOSED_TRADES:]
    # معايرة ذاتية لعمولة الصفقة الفعلية: نعاير متوسط الفرق (الرسوم
    # الكلية − السبريد المقيس عند الإغلاق) لأنه المكوّن الذي يمثل
    # العمولة فعلاً (السواب صفر هنا). تُخزَّن في state.perf
    # كـ measured_commission_usd ليصبح التقدير اللاحق أدق.
    try:
        _fees = rec.get("fees_usd")
        if _fees is not None:
            _fees = float(_fees)
        comm_est = max(0.0, _fees - float(rec.get("spread_usd") or 0.0))
        if comm_est and comm_est > 0:
            perf = state.setdefault("perf", {})
            _n = int(perf.get("measured_count") or 0)
            _old = float(perf.get("measured_commission_usd") or 0.0)
            _new = (_old * _n + comm_est) / (_n + 1)
            perf["measured_count"] = _n + 1
            perf["measured_commission_usd"] = round(_new, 4)
    except (TypeError, ValueError):
        pass
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
    """تسجيل إغلاق خارجي (من المستخدم أو السيرفر).

    لا نخمّن PnL هنا (كان سبباً لتلوّث البيانات سابقاً). نسجل الصفقة
    بقيم الأسعار فقط وPnL صفر، عدا الحالة التي نتوفر فيها على pnl محسوب
    فعلي عبر pnl_last_usd.
    """
    st_pos = state.get("position") or {}
    tracked_pnl = st_pos.get("pnl_last_usd")
    try:
        tracked_pnl = float(tracked_pnl) if tracked_pnl is not None else 0.0
    except (TypeError, ValueError):
        tracked_pnl = 0.0
    if ts_open:
        rec = {
            "ts_open": ts_open,
            "ts_close": ts_close,
            "side": st_pos.get("side"),
            "entry_gap": entry_gap,
            "close_gap": gap,
            "entry_price": entry_price,
            "close_price": close_price,
            "pnl_units": round(tracked_pnl, 2),
            "pnl_usd": round(tracked_pnl, 2),
            "fees_usd": 0.0,
            "pnl_net_usd": round(tracked_pnl, 2),
            "reason": "external_close",
            "pnl_peak_usd": round(float(st_pos.get("pnl_peak_usd") or 0), 2),
        }
        _record_close(state, rec)
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
    """الدورة الرئيسية للتداول مع فحص جميع طبقات الإغلاق.
    
    التدفق المنطقي:
    1. جلب المواقع من API (مع الاعتماد على الكاش عند الفشل)
    2. إذا وُجدت مواقع → فحص الإغلاق عبر check_close (5 طبقات)
    3. إذا لم تكن هناك مواقع ولكن state يحتوي positionId → إغلاق قسري
    4. إذا لم تكن هناك صفقة مفتوحة → قرار الفتح (مع منع التعدد)
    5. عدم مسح state["position"] إلا بعد التأكد من عدم وجود صفقة فعليّة
    """
    symbol_id = result["symbol_id"]
    # تخزين السبريد الحي في state ليُستخدم من check_close (بلا تمرير result)
    # ومن state-force-close — قياس التكلفة دائماً من آخر bid/ask.
    state["_last_spread_usd"] = _detected_spread_usd(result)
    try:
        # IMPORTANT: open_positions(account_id) — نمرر self.account_id لا symbol_id!
        positions = yield sess.open_positions(sess.account_id, max_age=86400.0)
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
            result["z"] = (mid - centre) / scale

    now_ts = time.time()
    md = state.get("money_digits")
    if not md:
        md = result.get("money_digits") or 2
        state["money_digits"] = md
    entry_units = state.get("entry_balance_units")

    side = None
    action = "none"
    closed_this_cycle = False

    # =========================================================================
    # مرحلة الإغلاق: نحدد ما إذا كنا نغلق صفقة حاليّة
    # =========================================================================
    pos_for_close = None
    if positions:
        pos_for_close = positions[0]
    elif state.get("position") is not None and isinstance(state["position"], dict):
        # API أعاد empty لكن state يحتوي position → نحاول إصلاح
        # positionId إن كان مفقوداً ثم إغلاق قسري للصفقة المعلقة.
        sp = state["position"]
        opened_at = sp.get("opened_at")
        if opened_at:
            try:
                opened_dt = datetime.fromisoformat(opened_at)
                age_sec = (datetime.now(timezone.utc) - opened_dt).total_seconds()
            except Exception:
                age_sec = 1e9
                opened_dt = None
            if age_sec < 120:
                print(f"skip state-force-close: position only {age_sec:.0f}s old — wait for API sync")
                result["action"] = "hold:recently_opened"
                closed_this_cycle = False
            else:
                p_id = sp.get("positionId")
                if not p_id and opened_dt is not None:
                    # استرجاع الـ positionId الحقيقي من سجل الأوامر
                    try:
                        p_id = yield sess.resolve_position_id(
                            sess.account_id, opened_dt.timestamp(),
                            sp.get("entry_price"),
                            sp.get("side") or "BUY",
                            config.SL_AFTER_ENTRY_USD,
                        )
                    except Exception:
                        p_id = None
                    if p_id:
                        sp["positionId"] = p_id
                        print(f"state positionId recovered: {p_id}", flush=True)
                        state["position"] = sp
                if p_id:
                    # القواعد من state وحده (لا positions من API) — الوضع
                    # "local-state" هو الوضع الفعلي (open_positions لا يعيد
                    # قائمة)، لذلك يجب أن تُطبّق هنا طبقات الحماية الكاملة
                    # (max_loss / profit_target / trailing / z_revert / سقف
                    # المدة / شذوذ البيانات). الإغلاق القديم كان ينتظر فقط
                    # جبرياً gap_closed (متعطل sltp_set) أو 2.5 ساعة أو 22$
                    # أي خسارة -24.12 في 09:18 بدل قطعها عند -6.
                    try:
                        age_sec_now = (datetime.now(timezone.utc)
                                       - opened_dt).total_seconds()
                    except Exception:
                        age_sec_now = 1e9
                    entry_price = sp.get("entry_price")
                    side_name = str(sp.get("side", "BUY")).upper()
                    digits = state.get("money_digits", 2) or 2
                    volume_close = int(round(
                        (getattr(config, "LOT", 0.01) or 0.01) * 10000.0
                    )) or result.get("volume", 100)
                    pnl_now = 0.0
                    _sfees = 0.0
                    if entry_price:
                        price_diff = mid - entry_price
                        if side_name == "SELL":
                            price_diff = -price_diff
                        gross_now = (price_diff * volume_close) / (10.0 ** digits)
                        # التكلفة الفعلية للصفقة: عمولة (فعلية/معايرة) +
                        # سواب + السبريد الحي المقيس — تُخصم دائماً من الربح
                        # ليُقرر الإغلاق على الربح الصافي بعد التكلفة.
                        pos_fake = types.SimpleNamespace(
                            price=entry_price, tradeData=types.SimpleNamespace(
                                volume=volume_close,
                                tradeSide=(2 if side_name == "SELL" else 1)),
                            commission=getattr(sp, "commission", 0),
                            swap=getattr(sp, "swap", 0),
                        )
                        _sfees = position_fees_usd(
                            pos_fake, digits, result=result, state=state)
                        pnl_now = gross_now - _sfees
                    # القمة تُقرأ من الحالة وتبدأ من 0.0 (صافي أعلى ربح)
                    # وتُحفظ في فرع الاحتفاظ أدناه حتى لا تبقى قديمة —
                    # التريلنج يحتاج قمة حية عبر الدورات ليعمل.
                    _spk = sp.get("pnl_peak_usd")
                    peak_now = float(_spk) if _spk is not None else 0.0
                    peak_now = max(peak_now, 0.0)
                    peak_now = max(peak_now, pnl_now)
                    # طبقات الإغلاق — نفس معايير ClosingManager.check_close
                    close_reason_state = None
                    trailing_armed = (
                        config.TRAILING_ARM_USD > 0
                        and peak_now >= config.TRAILING_ARM_USD
                        and config.TRAILING_BACK_USD > 0
                    )
                    if trailing_armed and pnl_now >= 0 and \
                            (peak_now - pnl_now) >= config.TRAILING_BACK_USD:
                        close_reason_state = "trailing"
                    if close_reason_state is None and \
                            config.PROFIT_TARGET_USD > 0 and \
                            pnl_now >= config.PROFIT_TARGET_USD:
                        close_reason_state = "profit_target"
                    if close_reason_state is None and \
                            pnl_now <= -config.MAX_LOSS_USD:
                        close_reason_state = "max_loss"
                    if close_reason_state is None and age_sec_now > max_age:
                        close_reason_state = "max_hold_time"
                    # القاعدة الجذرية 2026-09-16: أي صفقة بلا SL/TP سيرفر
                    # تُغلق قسراً فور تجاوز الدقائق الأولى — لا معلّق أبداً
                    # حتى لو توقف البوت بعدها (السيرفر هو الضامن الفعلي).
                    if close_reason_state is None and \
                            not sp.get("sltp_set") and \
                            age_sec_now > 120:
                        close_reason_state = "no_broker_stops"
                    # (الارتداد z_revert أُزيل 2026-09-16 — مركز القناة نقطة
                    # بدء اللحاق لا خروجه؛ نظام الإغلاق الجديد: ستوب/TP سيرفر
                    # + تريلنج فوق الهدف.)
                    max_age = config.MAX_HOLD_HOURS * 3600
                    # حارس شذوذ: قفزة غير صحية في سعر المنصة خلال ~80 ثانية
                    # (تكاد مستحيلة في الذهب) — تعني خلل شريط/سيولة. لا نستخدم
                    # |gap| لأن الفجوة تختلف بنيوياً حسب مصدر global (ياهو
                    # GC=F ≈ 37$ أعلى من السبوت) وستُغلق كل صفقة خطأً.
                    # قفزة ياهو (momentum) = سوق حقيقي، لذلك نعتمد على قفزة
                    # المنصة نفسها فقط لالتقاط أخطاء بيانات cTrader.
                    price_jump = abs(result.get("platform_momentum", 0.0))
                    price_anomaly = price_jump >= config.PRICE_JUMP_ANOMALY_USD
                    if close_reason_state is not None or price_anomaly:
                        try:
                            yield sess.close_position(
                                p_id,
                                volume=None,
                                max_retries=3,
                            )
                            if entry_price:
                                gross_pnl_close = (price_diff * volume_close) / (10.0 ** digits)
                                pnl_net_close = round(gross_pnl_close - _sfees, 2)
                                sp["pnl_last_usd"] = pnl_net_close
                                sp["pnl_peak_usd"] = max(float(sp.get("pnl_peak_usd", 0)), pnl_net_close)
                                print(f"✓ CLOSED (state-force-close/{close_reason_state or 'price_anomaly'}): pnl={pnl_net_close:.2f} USD (fees={_sfees:.2f})")
                            else:
                                pnl_net_close = 0.0
                                print("✓ CLOSED (state-force-close): no entry_price — PnL=0")
                            result["action"] = "close:state-force-close"
                            result["close_pnl_usd"] = pnl_net_close
                            state["position"] = None
                            state["cooldown_until"] = now_ts + config.COOLDOWN_MINUTES * 60
                            if pnl_net_close > 0:
                                closing_mgr.record_win(pnl_net_close)
                            else:
                                closing_mgr.record_loss(pnl_net_close)
                            closing_mgr.save_perf_to_state(state)
                            _record_close(state, {
                                "ts_open": sp.get("opened_at"),
                                "ts_close": utcnow_iso(),
                                "side": side_name,
                                "entry_gap": sp.get("entry_gap"),
                                "close_gap": gap,
                                "entry_price": entry_price,
                                "close_price": mid,
                                "pnl_units": pnl_net_close,
                                "pnl_usd": pnl_net_close,
                                "fees_usd": round(_sfees, 2),
                                "spread_usd": round(_detected_spread_usd(result), 2),
                                "pnl_net_usd": pnl_net_close,
                                "reason": close_reason_state or "price_anomaly",
                                "pnl_peak_usd": round(float(sp.get("pnl_peak_usd", 0)), 2),
                            })
                            result["close_pnl_usd"] = pnl_net_close
                            closed_this_cycle = True
                        except Exception as exc:
                            msg = repr(exc)
                            if "POSITION_NOT_FOUND" in msg:
                                print(" state-force: broker already closed "
                                      "position; reconciling (external)",
                                      flush=True)
                                state["position"] = None
                                state["cooldown_until"] = (
                                    now_ts + config.COOLDOWN_MINUTES * 60
                                )
                                result["action"] = "close:external-reconciled"
                            else:
                                print(f"state-force-close failed: {exc!r}")
                                result["action"] = "close_pending:state"
                    else:
                        # حفظ القمة الحية في الحالة — بعدها يقرأ التريلنج
                        # القمة الحقيقية الصافية لا القيمة القديمة.
                        sp["pnl_peak_usd"] = round(peak_now, 2)
                        sp["pnl_last_usd"] = round(pnl_now, 2)
                        print(f"state-hold: pnl={pnl_now:.2f} "
                              f"peak={peak_now:.2f} "
                              f"age={age_sec_now/3600:.1f}h — keeping",
                              flush=True)
                        result["action"] = "hold:state"
                        closed_this_cycle = False
                else:
                    print("state position: no positionId and none recoverable — cannot close yet", flush=True)
                    result["action"] = "hold:no-posid"
                    closed_this_cycle = False
        else:
            p_id = sp.get("positionId")
            if p_id:
                try:
                    yield sess.close_position(p_id, volume=None, max_retries=3)
                    state["position"] = None
                    state["cooldown_until"] = now_ts + config.COOLDOWN_MINUTES * 60
                    result["action"] = "close:state-force-close"
                    closed_this_cycle = True
                except Exception as exc:
                    msg = repr(exc)
                    if "POSITION_NOT_FOUND" in msg:
                        print(" state-force: broker already closed position; "
                              "reconciling state", flush=True)
                        state["position"] = None
                        state["cooldown_until"] = (
                            now_ts + config.COOLDOWN_MINUTES * 60
                        )
                        result["action"] = "close:external-reconciled"
                    else:
                        print(f"state-force-close failed: {exc!r}")
                        result["action"] = "close_pending:state"
            else:
                result["action"] = "hold:no-posid"
                closed_this_cycle = False

    # =========================================================================
    # إذا لم نعثر على position من API (وضع state-only)، نبنيه من الحالة
    # ذاتها كي تُفحص طبقات الإغلاق كاملة (تريلنج/TP/SL/الزمن/الارتداد)
    if pos_for_close is None:
        spo = state.get("position")
        if isinstance(spo, dict) and spo.get("positionId"):
            pos_for_close = types.SimpleNamespace(
                positionId=spo["positionId"],
                digits=state.get("money_digits", 2) or 2,
                price=spo.get("entry_price"),
                tradeData=types.SimpleNamespace(
                    volume=int(round(
                        (getattr(config, "LOT", 0.01) or 0.01) * 10000.0
                    )),
                    tradeSide=(
                        1 if str(spo.get("side", "BUY")).upper() == "BUY"
                        else 2
                    ),
                ),
            )

    # ملاحظة: البروكر (FP Markets) يرفض تعديل SL/TP لصفقة مفتوحة
    # (ProtoOAAmendPositionSLTPReq -> TRADING_BAD_STOPS دائماً، تحقق تجريبي).
    # الحماية تُعطى الآن حصراً من لحظة الفتح عبر sl/tp داخل الـ open request.
    # صفقة قديمة (sltp_set=False) تُدار بالطبقات فقط ولا تُسد بضبط وسيط.
    if pos_for_close is not None and not state.get("position", {}).get("sltp_set"):
        print("  broker disable amending SL/TP on open positions — "
              "protect only at open request time; layers still manage "
              "this one", flush=True)

    # إذا كانت هناك صفقة مفتوحة (من API أو حالة قسريّة)، فحص الإغلاق
    # =========================================================================
    if pos_for_close is not None:
        # حارس الشذوذ: ملء قفزة سعر المنصة اللحظية في الحالة ليستخدمها
        # check_close و state-force-close. نعتمد على platform_momentum فقط
        # (قفزة ياهو = سوق حقيقي لا تُغلق).
        state["_anomaly_jump"] = abs(result.get("platform_momentum", 0.0))
        pos = pos_for_close
        st_pos = state.get("position")
        if st_pos is None:
            st_pos = {}
            state["position"] = st_pos
        if not isinstance(st_pos, dict):
            st_pos = {}
            state["position"] = st_pos

        # تحديث st_pos بالبيانات الجديدة من الـ API
        st_pos["positionId"] = pos.positionId
        st_pos["side"] = _side_name(pos.tradeData.tradeSide)
        # ملاحظة: open_positions يعيد ProtoOAOrder (بلا سعر).
        # نحافظ على entry_price من الـ state — السعر الموثوق الوحيد.
        raw_price = getattr(pos, "price", None)
        if raw_price is not None and raw_price > 10000:
            raw_price = raw_price / config.SPOT_SCALE
        st_pos["entry_price"] = st_pos.get("entry_price") or raw_price or mid
        # الحفاظ على pnl_peak_usd و pnl_track من الـ state
        st_pos.setdefault("pnl_peak_usd", 0.0)
        st_pos.setdefault("pnl_track", [])
        state["position"] = st_pos

        # --- فحص جميع طبقات الإغلاق ---
        should_close, close_reason = closing_mgr.check_close(
            pos, mid, global_price, stats, st_pos, now_ts, md,
        )
        result["close_check"] = {
            "should_close": should_close,
            "reason": close_reason,
        }

        if should_close and close_reason:
            # إنسانية: تأخير رد فعل قبل الإغلاق الاختياري (ربح/تريلنج/
            # ارتداد) ليبدو القرار بشرياً. أما حدود الأمان (max_loss/
            # price_anomaly) فتُنفّذ فوراً بلا تأخير — حماية رأس المال
            # لا تُمَس. القاعدة 2.
            if (close_reason in ("trailing", "profit_target", "z_revert")
                    and config.HUMANIZE_ON):
                _rclose = _human_reaction() * 0.5
                if _rclose > 0:
                    yield deferLater(reactor, _rclose, lambda: None)
            try:
                yield sess.close_position(
                    pos.positionId,
                    volume=getattr(pos.tradeData, "volume", None),
                    max_retries=3,
                )
                closed_this_cycle = True

                # حساب PnL الحقيقي
                entry_price = st_pos.get("entry_price")
                close_price = mid
                side_name = _side_name(pos.tradeData.tradeSide)
                volume = getattr(pos.tradeData, "volume", 100)
                digits = getattr(pos, "digits", 2) or 2

                price_diff = close_price - entry_price if entry_price else 0
                if side_name == "SELL":
                    price_diff = -price_diff
                gross_pnl = (price_diff * volume) / (10.0 ** digits)
                fees_est = position_fees_usd(
                    pos, digits, result=result, state=state) if digits else 0
                pnl_net = round(gross_pnl - fees_est, 2)

                print(
                    f"✓ CLOSED (layer: {close_reason}): "
                    f"pnl={pnl_net:.2f} USD (gross={gross_pnl:.2f}), "
                    f"peak={float(st_pos.get('pnl_peak_usd', 0)):.2f} USD, "
                    f"entry_price={entry_price}, close_price={close_price:.2f}"
                )

                result["action"] = "close:" + close_reason
                state["position"] = None
                # إنسانية (القاعدة 1): فترة التهدئة ليست ثابتة بالثانية —
                # تشتت ±15% حتى لا تظهر أنماط إعادة دخول منتظمة.
                _cd = config.COOLDOWN_MINUTES * 60
                if config.HUMANIZE_ON:
                    import random as _rr
                    _cd *= _rr.uniform(0.85, 1.15)
                state["cooldown_until"] = now_ts + _cd
                if pnl_net > 0:
                    closing_mgr.record_win(pnl_net)
                else:
                    closing_mgr.record_loss(pnl_net)
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
                    "spread_usd": round(_detected_spread_usd(result), 2),
                    "pnl_net_usd": pnl_net,
                    "reason": close_reason,
                    "pnl_peak_usd": round(
                        float(st_pos.get("pnl_peak_usd") or 0), 2,
                    ),
                })
                result["close_pnl_usd"] = pnl_net
            except Exception as exc:
                msg = repr(exc)
                if "POSITION_NOT_FOUND" in msg:
                    # الوسيط أغلق الصفقة بنفسه (ستوب/هدف/إيقاف يدوي):
                    # state قديم، لا ننتظر رنات إضافية تعيد نفس المحاولة
                    print("  POSITION_NOT_FOUND — broker already closed "
                          "the position; reconciling state (external close)",
                          flush=True)
                    entry_x = st_pos.get("entry_price")
                    if entry_x:
                        close_x = mid
                        diff = close_x - entry_x
                        if _side_name(pos.tradeData.tradeSide) == "SELL":
                            diff = -diff
                        pnl_x = round((diff * volume) / (10.0 ** (digits or 2)), 2)
                        if pnl_x > 0:
                            closing_mgr.record_win(pnl_x)
                        else:
                            closing_mgr.record_loss(pnl_x)
                        closing_mgr.save_perf_to_state(state)
                        _record_close(state, {
                            "ts_open": st_pos.get("opened_at"),
                            "ts_close": utcnow_iso(),
                            "side": _side_name(pos.tradeData.tradeSide),
                            "entry_gap": st_pos.get("entry_gap"),
                            "close_gap": gap,
                            "entry_price": entry_x,
                            "close_price": close_x,
                            "pnl_units": pnl_x,
                            "pnl_usd": pnl_x,
                            "fees_usd": 0,
                            "pnl_net_usd": pnl_x,
                            "reason": "external-close-reconciled",
                            "pnl_peak_usd": round(
                                float(st_pos.get("pnl_peak_usd") or 0), 2,
                            ),
                        })
                    state["position"] = None
                    state["cooldown_until"] = now_ts + config.COOLDOWN_MINUTES * 60
                    result["action"] = "close:external-reconciled"
                    result["close_pnl_usd"] = round(
                        locals().get("pnl_x", 0) or 0, 2)
                else:
                    result["close_failed"] = repr(exc)
                    print(f"close_position failed (layer: {close_reason}): {exc!r}")
                    result["action"] = "close_pending"
        else:
            result["action"] = "hold"

    # =========================================================================
    # مرحلة الفتح: لا تفتح إلا إذا لم تكن هناك صفقة مفتوحة فعليّة
    # =========================================================================
    # NOTICE: لا نعتمد على positions فقط — إذا فشل API، positions قد يكون []
    # لكن state["position"] فقط إذا كان لديه positionId صحيح يوضح وجود صفقة
    state_pos = state.get("position")
    state_pos_live = (
        isinstance(state_pos, dict) and any(state_pos)
    )
    # حارس صارم: نمنع الفتح إذا وُجدت أي صفقة (من API أو الحالة أو كاش آخر)
    # يجب ألا نفتح صفقة جديدة قبل التأكد التام من عدم وجود صفقات مفتوحة.
    has_open_position = bool(positions) or bool(state_pos_live)
    cache_positions = list(getattr(sess, "last_positions", None) or [])
    if cache_positions:
        has_open_position = True

    if not has_open_position and not closed_this_cycle:
        cooldown_left = state.get("cooldown_until", 0) - now_ts
        in_session_now = in_session(datetime.now(timezone.utc))
        quality_session_now = in_quality_session(datetime.now(timezone.utc))

        # حارس الاتجاه: نمنع الدخول عندما يكون انحدار سعر المنصة (المدى الطويل)
        # معاكساً لاتجاه زخم الدخول بقوة (كسر اللحاق المؤكد). الشرط:
        # slope * signal < 0 و abs(slope) يتجاوز الحد.
        trend = result.get("trend_slope", 0.0)
        momentum = result.get("momentum", 0.0)       # زخم ياهو GC=F (القائد)
        plat_mom = result.get("platform_momentum", 0.0)  # زخم المنصة (التابع)
        # إشارة اللحاق: الفرق بين حركة ياهو وحركة المنصة على نفس النافذة.
        # ياهو (عقود آجلة COMEX) يتحرك أولاً والمنصة (سبوت) تلحق متأخرة —
        # فإذا تقدم ياهو +2$ والمنصة +0.5$ فقط، بقي +1.5$ لحاقاً محتملاً.
        catch_up = momentum - plat_mom
        slope_against_signal = (
            (trend * catch_up) < 0
        )
        trend_against = (
            config.TREND_ON
            and slope_against_signal
            and abs(trend) > config.TREND_MAX_SLOPE_USD
        )

        # التكلفة الفعلية للصفقة المتوقعة من آخر قياس (سبريد حي + عمولة
        # معايرة/فعلية + سواب). تُستخدم للتأكد أن الإشارة تتجاوز التكلفة
        # — وإلا تكون الصفقة خاسرة من البداية (2026-09-15).
        _live_spread = _detected_spread_usd(result)
        _est_fees = _live_spread + _commission_usd(None, state=state) \
            if _live_spread > 0 else 0.0

        # تأكيد ثلاث دورات (2026-09-21 — نقاط دخول أقوى دون خفض العدد):
        # كان تأكيد دورتين. الآن لا ندخل إلا إذا استمرت إشارة اللحاق بنفس
        # الاتجاه بقوة في الدورات 3 المتتالية الأخيرة (~15 ثانية) — يؤخر
        # الدخول لحظياً ويقتل الومضات القصيرة جداً دون حرمان كبير من
        # الدخولات المشروعة (الاتجاه القوي يبقى عدة دقائق). تُخزَّن في
        # state فتبقى مستمرة عبر الجلسات (تُحفظ دورياً).
        _prev2_catch = state.get("_prev2_catch_up")
        _prev_catch = state.get("_prev_catch_up")
        _confirm_ok = (
            _prev_catch is not None
            and _prev2_catch is not None
            and (_prev_catch * catch_up) >= 0
            and (_prev2_catch * catch_up) >= 0
            and abs(_prev_catch) >= 0.85 * config.MOMENTUM_MIN_USD
            and abs(_prev2_catch) >= 0.85 * config.MOMENTUM_MIN_USD
        )
        state["_prev2_catch_up"] = _prev_catch
        state["_prev_catch_up"] = catch_up

        signal_ready = (
            config.MOMENTUM_ON
            and abs(catch_up) >= config.MOMENTUM_MIN_USD
            and abs(momentum) >= 0.5 * config.MOMENTUM_MIN_USD
            # الإشارة يجب أن تغطي التكلفة (سبريد+عمولة) وتبقى ربحاً محتملاً:
            # نمنع الدخول عندما تلتهم التكلفة الزخم (جودة سلبية مضمونة).
            and abs(catch_up) > (_est_fees * 2.0)
            and _confirm_ok
        )

        # إنسانية (القاعدة 4): أحياناً يُفوّت المتداول إشارة صالحة —
        # لا يلتقط كل شيء بصورة آلية. يُقيَّم مرة لكل دورة.
        human_skip = _skip_signal()

        # حارس السبريد: لا ندخل إذا كان السبريد الحي واسعاً جداً (تذبذب
        # لحظي خارجي/سيولة شاذة) — البيت السعري مكلف زائداً (2026-09-15).
        spread_wide = (
            config.SPREAD_GUARD_USD > 0
            and _live_spread >= config.SPREAD_GUARD_USD
        )

        can_trade = (
                config.MODE == "trade"
                and stats is not None
                and signal_ready
                and not human_skip
                and not spread_wide
                and result.get("balance_usd", 0) >= config.MIN_BALANCE_TO_TRADE
                and cooldown_left <= 0
                and in_session_now
                and quality_session_now
                and result.get("platform_jump", 0.0) < config.PRICE_JUMP_ANOMALY_USD
                and not trend_against
                and state_pos is None
                and closing_mgr.can_trade_today()
            )

        if can_trade:
            if positions:
                result["action"] = "hold:already_open"
                result["open_positions"] = len(positions)
            else:
                # --- فتح صفقة جديدة ---
                # الإشارة = مقدار اللحاق المتبقي (catch_up):
                #   catch_up = زخم ياهو − زخم المنصة.
                # ياهو GC=F (عقود آجلة COMEX) يقود والمنصة (سبوت) تلحق،
                # فإذا تحرك ياهو والمنصة لم تلحق بعد → نفتح باتجاه ياهو
                # متوقعين لحاق المنصة. catch_up>0 → BUY، <0 → SELL.
                side = "SELL" if catch_up < 0 else "BUY"
                sd = (
                    stats.get("mad") if config.USE_MAD
                    else stats["sd"]
                )
                sd = sd or stats["sd"]
                # إنسانية: لا يضع المتداول وقفاً عند نفس المسافة الحرفية
                # كل مرة — تشتت بسيط على المسافة ضمن حدود آمنة (القاعدة 1).
                sl_dist = _jitter_usd(config.SL_AFTER_ENTRY_USD,
                                      config.HUMAN_SL_TP_JITTER_USD)
                # الهدف (نظام الإغلاق 2026-09-16): لا نقطع اللحاق عند 1.00
                # الثابت — نأخذ نصيباً عادلاً منه. حد أدنى 1.40$ (عند لوت
                # 0.01 = 1.4 نقطة) و50% من مقدار اللحاق للموجات القوية،
                # فيثبّت ربحاً حقيقياً قبل أي انعكاس (بيانات 185 صففة:
                # خروج 1.00 يترك 0.2-0.6$ لكل صفقة على الطاولة).
                min_tp_dist = 1.40
                tp_ext = max(min_tp_dist, 0.50 * abs(catch_up))
                if side == "SELL":
                    sl = mid + sl_dist
                    tp = mid - tp_ext
                else:
                    sl = mid - sl_dist
                    tp = mid + tp_ext
                print(
                    f"order-request side={side} mid={mid:.2f} "
                    f"sl={sl:.2f} tp={tp:.2f} sl_dist={sl_dist:.2f} "
                    f"gap={gap:.2f} yahoo_mom={momentum:+.2f} "
                    f"plat_mom={plat_mom:+.2f} catch_up={catch_up:+.2f} "
                    f"spread={_live_spread:.2f} fees~{_est_fees:.2f} "
                    f"tp_dist={tp_ext:.2f}"
                )
                # إنسانية: تأخير بشري قبل التنفيذ (محاكاة قرار المتداول)
                # — القاعدة 2. يؤخّر إرسال الطلب دون تغيير منطق الإشارة.
                _react = _human_reaction()
                if _react > 0:
                    print(f"human-reaction: waiting {_react:.1f}s "
                          f"before order", flush=True)
                    yield deferLater(reactor, _react, lambda: None)
                try:
                    trad_pre = yield sess.get_trader()
                except Exception:
                    trad_pre = None
                vol = _jittered_volume(result["volume"])
                # هام: البروكر (FP Markets) يرفض تعديل السول/الهدف بعد الفتح
                # (ProtoOAAmendPositionSLTPReq -> TRADING_BAD_STOPS دائماً؛
                #  تم التحقق تجريبياً بكل المقاييس والمسافات)، لذلك نرسل
                # الـ stopLoss/takeProfit داخل طلب الفتح نفسه، ويُقبل فوراً.
                # إنسانية (القاعدة 3): ملصق مقروء يشبه الاسم اليدوي — لا
                # يكشف المنطق (عدم ذكر yahoo/gap/momentum/الفجوة إطلاقاً).
                sl_units = _to_int(sl)
                tp_units = _to_int(tp)
                res = yield sess.open_market(
                    symbol_id, side, vol,
                    sl=sl_units, tp=tp_units,
                    label=_human_label(),
                    comment="",
                )
                stops_set = res.get("stops_set", True) if isinstance(res, dict) else True
                if not stops_set:
                    print("  WARN: broker did NOT accept SL/TP at open — "
                          "position will be force-closed within 2 min "
                          "(no_broker_stops)", flush=True)
                order = res["order"] if isinstance(res, dict) else res.order
                # تسجيل entry_price من order.executionPrice أو res.position.price
                order_exec_price = (
                    float(order.executionPrice)
                    if order and order.executionPrice else None
                )
                position_price = None
                pos_obj = res.get("position") if isinstance(res, dict) else getattr(res, "position", None)
                if pos_obj and getattr(pos_obj, "price", None):
                    position_price = float(pos_obj.price)
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
                    "orderId": getattr(order, "orderId", None),
                    "side": side,
                    "executionPrice": (
                        float(order.executionPrice)
                        if order and getattr(order, "executionPrice", None)
                        else None
                    ),
                    "tradeData": {
                        "volume": (
                            getattr(order.tradeData, "volume", None)
                            if order and getattr(order, "tradeData", None)
                            else None
                        ),
                        "label": (
                            getattr(order.tradeData, "label", None)
                            if order and getattr(order, "tradeData", None)
                            else None
                        ),
                    },
                }
                position_id_val = (
                    res.get("positionId") if isinstance(res, dict)
                    else getattr(getattr(res, "position", None), "positionId", None)
                )
                new_st_pos = {
                    "positionId": position_id_val,
                    "side": side,
                    "entry_gap": gap,
                    "entry_price": entry_price_val,
                    "opened_at": utcnow_iso(),
                    "pnl_peak_usd": 0.0,
                    "pnl_track": [],
                    "stop_loss": float(sl),
                    "take_profit": float(tp),
                    "sltp_set": bool(stops_set),
                }
                state["position"] = new_st_pos
                state["entry_balance_units"] = (
                    trad_pre.balance if trad_pre is not None else None
                )
                state["cooldown_until"] = 0
                # تحديث الأداء
                closing_mgr.trade_count_today += 1
                closing_mgr.save_perf_to_state(state)
                # ستوب/هدف مقبولان من لحظة الفتح داخل الطلب نفسه
                # (البروكر يرفض تعديل صفقة مفتوحة، أياً كانت القيم)
                if position_id_val:
                    print(f"  SL/TP set at open: sl={sl:.2f} tp={tp:.2f}",
                          flush=True)
                # Verify/fetch positionId if broker omitted it
                # (Open API 0.9.2 قد لا يعيد positionId في الـ response)
                if not position_id_val:
                    try:
                        time.sleep(1.5)
                        opened_unix = None
                        try:
                            opened_unix = datetime.fromisoformat(
                                new_st_pos["opened_at"]).timestamp()
                        except Exception:
                            pass
                        if opened_unix:
                            fetched_id = yield sess.resolve_position_id(
                                sess.account_id, opened_unix,
                                entry_price_val, side,
                                config.SL_AFTER_ENTRY_USD,
                            )
                            if fetched_id:
                                state["position"]["positionId"] = fetched_id
                                print(f"  VERIFY: recovered positionId="
                                      f"{fetched_id}", flush=True)
                    except Exception as exc:
                        print(f"  VERIFY: could not fetch positionId: {exc!r}", flush=True)
        else:
            reasons = []
            if config.MODE != "trade":
                reasons.append("mode!=trade")
            if stats is None:
                reasons.append("warmup")
            elif config.MOMENTUM_ON and \
                    abs(result.get("catch_up", 0.0)) < config.MOMENTUM_MIN_USD:
                reasons.append("catchup_small")
            elif config.MOMENTUM_ON and \
                    abs(result.get("catch_up", 0.0)) <= (_est_fees * 2.0):
                reasons.append("fees_cover")
            if spread_wide:
                reasons.append("spread_wide")
            if human_skip:
                reasons.append("human_skip")
            if result.get("balance_usd", 0) < config.MIN_BALANCE_TO_TRADE:
                reasons.append("balance_low")
            if cooldown_left > 0:
                reasons.append("cooldown_min")
            if not in_session_now:
                reasons.append("session_closed")
            if not quality_session_now:
                reasons.append("session_quality_blocked")
            if result.get("platform_jump", 0.0) >= config.PRICE_JUMP_ANOMALY_USD:
                reasons.append("price_anomaly")
            if trend_against:
                reasons.append("trend_against")
            # دائرة Daily Loss و Consecutive Losses
            if not closing_mgr.can_trade_today():
                reasons.append("circuit_breaker")
            result["action"] = "none:" + ",".join(reasons) if reasons else "none"

    return action


def _print_report(result, state):
    """طباعة تقرير النهاية لـ live.py."""
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

        # FORCE-TEST: اختبار يدوي فقط — يُعطّل تماماً أثناء التداول الحقيقي
        if (config.FORCE_TEST_OPEN
                and config.MODE != "trade"
                and config.ENVIRONMENT.strip().lower() == "demo"):
            try:
                existing = sess.open_positions(sess.account_id, max_age=86400.0)
                if existing:
                    print(f"FORCE-TEST SKIP (already open): "
                          f"{[p.positionId for p in existing]}")
                else:
                    res = sess.open_market(
                        symbol_id, "BUY", volume,
                        label="FORCE-TEST", comment="",
                    )
                    res = res if isinstance(res, dict) else getattr(res, "position", None)
                    pos_obj = res
                    pos_id = (res.get("positionId")
                              if isinstance(res, dict)
                              else getattr(res, "positionId", None))
                    print(f"FORCE-TEST OPEN OK positionId={pos_id}")
                    if pos_id:
                        pos_price = (res.get("position", {}).get("price")
                                     if isinstance(res, dict)
                                     else getattr(getattr(res, "position", None) or pos_obj, "price", None))
                        if pos_price is None:
                            pos_price = None
                        entry0 = float(pos_price) if pos_price else 0.0
                        if entry0 <= 0:
                            entry0 = mid
                        for dist, scale in (
                            (5.0, config.SPOT_SCALE),
                            (5.0, 100.0),
                            (0.5, 100.0),
                            (20.0, 100.0),
                            (50.0, 100.0),
                        ):
                            try:
                                sess.set_sltp(
                                    pos_id,
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
                            sess.close_position(pos_id)
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
