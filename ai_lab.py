# -*- coding: utf-8 -*-
"""مختبر التداول — اختبار خلفي + تقويم اقتصادي + ذاكرة خبرة للعقل.

2026-10-05: تحويل العقل من "يقترح ويطبّق مباشرة" إلى "يقترح ← يُختبر على
التاريخ ← يُطبّق فقط إن أثبت التفوق". هذا الفرق بين متداول هاوي وعقل
متداول: لا ت risking real money على تخمين.

الأجزاء:
  1) load_history()   — سجل الصفقات الغني (فيه entry_gap) من data/trades.csv
  2) backtest()       — إعادة تشغيل التاريخ بمعاملات مرشّحة
  3) compare()        — المرشّح مقابل الأساس (المعاملات الحيّة الحالية)
  4) professionalism()— درجة احتراف 0..100 من مقاييس الأداء
  5) Knowledge        — ذاكرة دائمة: الدروس + سجل الدرجة (data/ai_knowledge.md)
  6) fetch_calendar() — أحداث USD عالية التأثير (NFP/CPI/FOMC) للحجب

كل دوال الوحدة هنا لا ترمي استثناءً: أي فشل = بيانات أقل، لا توقف تداول.
"""
import csv
import json
import os
import time
import urllib.request

DATA = "data"
HISTORY_CSV = os.path.join(DATA, "trades.csv")
KNOWLEDGE_MD = os.path.join(DATA, "ai_knowledge.md")
CALENDAR_CACHE = os.path.join(DATA, "ai_calendar.md")


# ---------------------------------------------------------------------------
# 1) السجل التاريخي
# ---------------------------------------------------------------------------
def load_history():
    """صفقات تاريخية بصيغة غنية: {ts, hour, side, entry_gap, pnl}.

    data/trades.csv قد يكون 10 أعمدة (ts_open,ts_close,side,entry_gap,
    close_gap,entry_price,close_price,pnl_units,pnl_usd,reason) أو 12
    (مع pnl_net_usd). نتحقق من 둘 ونأخذ صافي الربح حيثما وُجد.
    """
    rows = []
    try:
        with open(HISTORY_CSV, "r", encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            for r in rd:
                ts = (r.get("ts_close") or "").strip()
                pnl = None
                for key in ("pnl_net_usd", "pnl_usd"):
                    if r.get(key):
                        try:
                            pnl = float(r[key])
                            break
                        except (TypeError, ValueError):
                            pass
                if pnl is None:
                    continue
                eg = None
                try:
                    eg = abs(float(r.get("entry_gap")))
                except (TypeError, ValueError):
                    eg = None
                rows.append({
                    "ts": ts,
                    "hour": int(ts[11:13]) if len(ts) >= 13 and ts[11:13].isdigit()
                            else None,
                    "side": (r.get("side") or "").strip().upper(),
                    "entry_gap": eg,
                    "pnl": pnl,
                    "reason": (r.get("reason") or "").strip(),
                })
    except Exception as exc:
        print("lab: history unavailable ({0!r})".format(exc), flush=True)
    return rows


def load_recent_feed():
    """آخر الصفقات من data/ai_feed.md (بلا entry_gap ⇒ تُستخدم للقياس فقط)."""
    rows = []
    try:
        with open(os.path.join(DATA, "ai_feed.md"), "r", encoding="utf-8") as f:
            for line in f:
                if "|" not in line or line.startswith("#"):
                    continue
                p = line.split("|")
                if len(p) < 3:
                    continue
                try:
                    rows.append({
                        "ts": p[0].strip(),
                        "hour": int(p[0][11:13])
                        if len(p[0]) >= 13 and p[0][11:13].isdigit() else None,
                        "side": p[1].strip().upper(),
                        "pnl": float(p[2]),
                        "tag": p[3].strip() if len(p) > 3 else "",
                    })
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass
    return rows


# ---------------------------------------------------------------------------
# 2) الاختبار الخلفي
# ---------------------------------------------------------------------------
def _clip_outcome(realized, target, stop):
    """تقريب صادق لتيجة صفقة تحت هدف/وقف جديدين.

    لا نملك مسار السعر كاملاً، فنعتمد قاعدة محافظِنة:
      * ربح محقق >= الهدف  ⇒ يُحسب على الهدف (لا أكثر).
      * خسارة محققة <= الوقف ⇒ تُحسب على الوقف (لا أقل).
      * غير ذلك            ⇒ النتيجة الفعلية كما هي.
    هذا يقلّل المبالغة فيRentended في الاتجاهين ⇒ مبالِغ متحفّظ.
    """
    if target and realized >= target:
        return target, "target"
    if stop and realized <= -stop:
        return -stop, "stop"
    return realized, "actual"


def backtest(params, rows=None, use_session=True):
    """يعيد التاريخ بمعاملات المرشّح ويعيد مقاييس الأداء.

    params: momentum_min, profit_target_usd, max_loss_usd, blocked_hours
    تُفلتر الصفقات كما يفعل المحرك الحيّ (عتبة + ساعات محظورة + نافذة
    الجلسة)، ثم تُقصّ النتائج على الهدف/الوقف الجديدين.
    """
    if rows is None:
        rows = load_history()
    mom = float(params.get("momentum_min") or 1.20)
    tgt = float(params.get("profit_target_usd") or 1.60)
    stop = float(params.get("max_loss_usd") or 2.00)
    blocked = set(params.get("blocked_hours") or [])

    sw = ew = None
    if use_session:
        try:
            import config
            if getattr(config, "SESSION_BLOCK_ON", False):
                sw = float(getattr(config, "SESSION_BLOCK_START_HOUR", 16.0))
                ew = float(getattr(config, "SESSION_BLOCK_END_HOUR", 22.0))
        except Exception:
            sw = ew = None

    def in_session(h):
        if sw is None or h is None:
            return False
        if sw <= ew:
            return sw <= h < ew
        return h >= sw or h < ew

    kept, skipped = [], 0
    for r in rows:
        eg = r.get("entry_gap")
        h = r.get("hour")
        if h is not None and (h in blocked or in_session(h)):
            skipped += 1
            continue
        if eg is not None and eg < mom:
            skipped += 1
            continue
        pnl, _how = _clip_outcome(r["pnl"], tgt, stop)
        kept.append(pnl)

    return _metrics(kept, skipped)


def _metrics(pnls, skipped=0):
    n = len(pnls)
    if n == 0:
        return {"n": 0, "net": 0.0, "win_rate": 0.0, "avg_win": 0.0,
                "avg_loss": 0.0, "payoff": 0.0, "expectancy": 0.0,
                "profit_factor": 0.0, "max_consec_loss": 0,
                "skipped": skipped}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    net = round(sum(pnls), 2)
    avg_w = round(sum(wins) / len(wins), 3) if wins else 0.0
    avg_l = round(sum(losses) / len(losses), 3) if losses else 0.0
    gp = round(sum(wins), 2)
    gl = round(abs(sum(losses)), 2)
    streak = best = 0
    for p in pnls:
        if p <= 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return {
        "n": n,
        "net": net,
        "win_rate": round(100.0 * len(wins) / n, 1),
        "avg_win": avg_w,
        "avg_loss": avg_l,
        "payoff": round(avg_w / abs(avg_l), 3) if avg_l else 0.0,
        "expectancy": round(net / n, 3),
        "profit_factor": round(gp / gl, 3) if gl else 0.0,
        "max_consec_loss": best,
        "skipped": skipped,
    }


def compare(candidate, baseline, min_n=15, min_edge=0.03):
    """هل يستحق المرشّح التطبيق؟ قرار مشروط بالعينة وأفضلية واضحة.

    القواعد (متحفّطة عمداً — الانحياز للتباين Minimise overfit):
      1) عيّنة لا تقل عن min_n (بلا ذلك النتيجة بلا معنى).
      2) التوقع لكل صفقة (expectancy) أعلى بهامش واضح.
      3) الربح الإجمالي لا يسوء.
      4) أطول سلسلة خسائر متتالية لا تتضخّم أكثر من 2.
    """
    if candidate.get("n", 0) < min_n:
        return False, "sample too small ({0} < {1})".format(
            candidate.get("n", 0), min_n)
    if candidate.get("expectancy", 0) <= baseline.get("expectancy", 0) + min_edge:
        return False, "expectancy not better ({0} vs {1})".format(
            candidate.get("expectancy"), baseline.get("expectancy"))
    if candidate.get("net", 0) < baseline.get("net", 0):
        return False, "net P/L worse ({0} vs {1})".format(
            candidate.get("net"), baseline.get("net"))
    if candidate.get("max_consec_loss", 0) > baseline.get("max_consec_loss", 0) + 2:
        return False, "loss streak worse ({0} vs {1})".format(
            candidate.get("max_consec_loss"), baseline.get("max_consec_loss"))
    if candidate.get("payoff", 0) < baseline.get("payoff", 0):
        return False, "payoff worse ({0} vs {1})".format(
            candidate.get("payoff"), baseline.get("payoff"))
    return True, "validated: exp {0} vs {1}, payoff {2} vs {3}, n={4}".format(
        candidate.get("expectancy"), baseline.get("expectancy"),
        candidate.get("payoff"), baseline.get("payoff"), candidate.get("n"))


def candidate_grid(rows=None, base_blocked=None, top=6):
    """مرشّحات **مقاسة** على التاريخ، مرتّبة حسب التوقع لكل صفقة.

    شبكة خشنة عمداً (3×3×3): الشبكة الدقيقة = overfit. الهدف أن يختار العقل
    من بين خيارات مُثبتة لا أن يخترع أرقاماً غير مختبَرة.
    """
    if rows is None:
        rows = load_history()
    if len(rows) < 30:
        return []
    blk = list(base_blocked or [])
    out = []
    for mom in (1.00, 1.20, 1.40):
        for tgt in (2.00, 2.80, 3.60):
            for stop in (1.00, 1.20, 1.60):
                p = {"momentum_min": mom, "profit_target_usd": tgt,
                     "max_loss_usd": stop, "blocked_hours": blk}
                m = backtest(p, rows)
                if m["n"] >= 30:
                    m["params"] = p
                    out.append(m)
    out.sort(key=lambda m: (-m["expectancy"], -m["profit_factor"]))
    return out[:top]


def robustness(metrics_list):
    """درجة متانة المرشّح: كم مرّة كان جيداً عبر تعديلات بسيطة؟

    متداول محترف لا يبني على رقم واحد؛ يطلب أن تبقى النتيجة موجبة تحت
    اضطراب صغير في المعاملات. نرجّح العيّنة الأضيق والأنسب.
    """
    if not metrics_list:
        return 0.0
    pos = sum(1 for m in metrics_list if m.get("expectancy", 0) > 0)
    return round(pos / float(len(metrics_list)), 3)


# ---------------------------------------------------------------------------
# 3) درجة الاحتراف
# ---------------------------------------------------------------------------
def professionalism(live_rows=None, min_trades=30):
    """درجة احتراف 0..100 من سلوك حيّ حقيقي (لا من اختبار خلفي).

    تُحتسب على آخر min_trades صفقة مغلقة: الاكتمال،-table):
      25 نقطة: صافي موجب
      25 نقطة: نسبة فوز >= 55%
      20 نقطة: payoff >= 1.0
      15 نقطة: التوقع لكل صفقة موجب
      15 نقطة: عامل الربح >= 1.3
    العتبات مشدودة عمداً: التحويل لحساب حقيقي يتطلب Consistent ربح.
    """
    rows = live_rows if live_rows is not None else load_recent_feed()
    if len(rows) < min_trades:
        return {"score": 0, "n": len(rows), "verdict": "insufficient data",
                "metrics": {}}
    pnls = [r["pnl"] for r in rows][-min_trades:]
    m = _metrics(pnls)
    score = 0
    score += 25 if m["net"] > 0 else 0
    score += 25 if m["win_rate"] >= 55 else int(25 * max(0.0, (m["win_rate"] - 35) / 20))
    score += 20 if m["payoff"] >= 1.0 else int(20 * max(0.0, m["payoff"]))
    score += 15 if m["expectancy"] > 0 else 0
    score += 15 if m["profit_factor"] >= 1.3 else int(
        15 * max(0.0, min(1.0, (m["profit_factor"] - 0.8) / 0.5)))
    score = int(max(0, min(100, score)))
    verdict = ("ready_for_review" if score >= 80 else
               "developing" if score >= 55 else "unsafe")
    return {"score": score, "n": m["n"], "verdict": verdict, "metrics": m}


# ---------------------------------------------------------------------------
# 4) ذاكرة الخبرة (دائمة)
# ---------------------------------------------------------------------------
def graduation_report(live_rows=None, min_trades=60):
    """تقرير التخرّج إلى حساب حقيقي — يُعرض، ولا ينفّذ شيئاً.

    🚫 لا يوجد أي مسار في هذا المشروع ينقل الحساب تلقائياً إلى المال
    الحقيقي. هذا التقرير仅仅 يُظهر ما إذا كان الأداء يستحق النقاش، والقرار
    قرار بشري صريح (إدخال يدوي لبيانات حساب حقيقي + تغيير إعدادات). أي
    كود "تشغيل تلقائي بحساب حقيقي" هنا عمداً غير موجود ولن يُضاف.

    معايير التخرّج (كلها على أداء حيّ، لا على اختبار خلفي):
      * 60 صفقة حية على الأقل
      * صافي موجب، ونسبة فوز >= 55%، payoff >= 1.0، عامل ربح >= 1.3
      * درجة احتراف >= 80
      * بلا سلسلة خسائر متتالية >= 6
    """
    rows = live_rows if live_rows is not None else load_recent_feed()
    prof = professionalism(rows, min_trades=30)
    m = prof.get("metrics") or {}
    checks = [
        ("sample >= 60 live trades", len(rows) >= 60, len(rows)),
        ("net P/L positive", m.get("net", 0) > 0, m.get("net")),
        ("win rate >= 55%", m.get("win_rate", 0) >= 55, m.get("win_rate")),
        ("payoff >= 1.0", m.get("payoff", 0) >= 1.0, m.get("payoff")),
        ("profit factor >= 1.3", m.get("profit_factor", 0) >= 1.3,
         m.get("profit_factor")),
        ("no 6+ loss streak", m.get("max_consec_loss", 99) < 6,
         m.get("max_consec_loss")),
        ("professionalism >= 80", prof.get("score", 0) >= 80,
         prof.get("score")),
    ]
    passed = sum(1 for _, ok, _ in checks if ok)
    return {
        "score": prof.get("score"),
        "verdict": prof.get("verdict"),
        "checks": [{"name": n, "pass": bool(ok), "value": v}
                   for n, ok, v in checks],
        "passed": passed,
        "total": len(checks),
        "auto_switch": False,
        "note": "Live-account promotion is MANUAL by design: no code path "
                "here moves money. Passing all checks only means the "
                "conversation is worth having.",
    }


def knowledge_append(entry):
    """يلحق درساً/قراراً بملف الخبرة الدائم data/ai_knowledge.md."""
    try:
        os.makedirs(DATA, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
        with open(KNOWLEDGE_MD, "a", encoding="utf-8") as f:
            f.write("- [{0}] {1}\n".format(stamp, entry))
        with open(KNOWLEDGE_MD, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 400:
            with open(KNOWLEDGE_MD, "w", encoding="utf-8") as f:
                f.writelines(lines[-380:])
    except Exception as exc:
        print("lab: knowledge write failed ({0!r})".format(exc), flush=True)


def knowledge_tail(n=30):
    """آخر الدروس — تُغذّى في سياق العقل ليكررها/يصحّحها."""
    try:
        with open(KNOWLEDGE_MD, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[-n:])[-2500:]
    except Exception:
        return ""


def knowledge_head():
    try:
        with open(KNOWLEDGE_MD, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[:6])
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 5) التقويم الاقتصادي
# ---------------------------------------------------------------------------
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
# نُبقي أحداث USD فقط. المصدر يرد 429 عند التكرار ⇒ خزّن 3 ساعات على الأقل
# (fetch_calendar) ولا نطمس كل ساعة.
_USD_MARKERS = ("fomc", "fed", "payroll", "employment change", "unemployment",
                "cpi", "pce", "ism", "retail sales", "gdp", "jobless",
                "nonfarm", "core m/m", "initial claims", "consumer confidence",
                "philadelphia", "durable goods", "fed chair", "powell")
_NON_USD = ("boj", "boe", "ecb", "rba", "rbnz", "boc", "snb", "boerse",
            "german", "uk ", "u.k.", "europe", "japan", "china", "australia",
            "canada", "swiss", "mexico", "brazil", "india", "south africa")


def _is_usd_relevant(country, title):
    """هل الحدث مؤثّر على الذهب/الدولار؟ (USD فقط —/USD = محرّك الذهب)"""
    t = (title or "").lower()
    c = (country or "").lower()
    for bad in _NON_USD:
        if bad in t:
            return False
    if "united states" in c or c in ("usd", "usa", "u.s.", "us"):
        return True
    return any(m in t for m in _USD_MARKERS)


def fetch_calendar(max_age_min=180):
    """أحداث USD عالية التأثير القريبة (NFP/CPI/FOMC). تُخزَّن كـ md دائم.

    يفشل بصمت (Ret []): تقويم ناقص أفضل من تعطيل التداول. يخزّن ساعة
    واحدة على الأقل ⇒ لا ي hammering للمصدر (الذي يرد 429).
    """
    # 1) ذاكرة مؤقتة على القرص
    try:
        if (time.time() - os.path.getmtime(CALENDAR_CACHE)) < max_age_min * 60:
            with open(CALENDAR_CACHE, "r", encoding="utf-8") as f:
                cached = json.loads(f.read() or "[]")
            # نُعيد الترشيح عند القراءة حتى لا يبقى ملف قديم未经 الترشيح
            return [e for e in cached
                    if _is_usd_relevant(e.get("country"), e.get("title"))]
    except Exception:
        pass
    # 2) الشبكة
    try:
        req = urllib.request.Request(CAL_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    except Exception as exc:
        print("lab: calendar fetch warn ({0!r})".format(exc), flush=True)
        return []
    out = []
    for e in raw:
        try:
            if str(e.get("impact", "")).lower() != "high":
                continue
            country = (e.get("country") or "").strip()
            title = (e.get("title") or "").strip()
            if not _is_usd_relevant(country, title):
                continue
            out.append({"date": e.get("date"), "title": title,
                        "country": country, "forecast": e.get("forecast"),
                        "previous": e.get("previous")})
        except Exception:
            continue
    out.sort(key=lambda x: str(x.get("date") or ""))
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(CALENDAR_CACHE, "w", encoding="utf-8") as f:
            f.write(json.dumps(out))
    except Exception:
        pass
    return out


def event_blackout(events=None, minutes_before=20, minutes_after=25,
                   now=None):
    """هل نحن داخل نافذة حجبAround حدث عالي التأثير؟

    نافذة واسعة قبل/بعد لأن الخوف يتسرّب: أ Wider=20د قبل و25د بعد
    (تطابق سلوك متداول محترف: لا يدخل قبل خبر بـ 20 دقيقة).
    """
    if now is None:
        now = time.time()
    try:
        import datetime as _dt
        for e in (events if events is not None else fetch_calendar()):
            ds = str(e.get("date") or "")
            if not ds:
                continue
            t = _dt.datetime.fromisoformat(ds.replace("Z", "+00:00")).timestamp()
            if t - minutes_before * 60 <= now <= t + minutes_after * 60:
                return True, e
    except Exception:
        return False, None
    return False, None


def _write_text(path, text):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
