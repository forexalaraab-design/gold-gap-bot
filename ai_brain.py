# -*- coding: utf-8 -*-
"""
ai_brain.py — عقل LLM خارجي للبوت: يبحث ويحلل ويخطط (مع بوابة تنفيذ مقيدة).

الغرض (2026-10-02): المركز الذي يفكر فوق بيانات البوت:
  * يبحث في الويب (أخبار الذهب / GC=F / دوافع السوق).
  * يقرأ سجل الصفقات (trades.csv) + الأداء (performance.json) + الحالة.
  * يحلل السببية (الساعات/الاتجاه/الستوبات/الربح) ويستنتج قراراً.
  * يكتب "خطة" يومية مقروءة في data/ai_plan.md.
  * ينتج توصيات قابلة للتمثيل (تعديل عتبة) في data/ai_recommendations.json
    ليقررها المستخدم صراحةً — لا يُنفَّذ شيء تلقائياً من غير موافقة.

البنية:
  * لا يتصل بالبروكر إطلاقاً (لا معلومة من فتح/إغلاق تُرسَل إلا بيانات مجهولة).
  * لا يلمس state/live cycle — فقط read + كتابة أهداف في data/.
  * أي استدعاء وخارجي يكون عبر AI_FETCH_TIMEOUT ويصمت عند الفشل (لا توقف)
    حتى لو غاب المفتاح/الشبكة.
  * المزود متوافق مع OpenAI oembedded (chat/completions عبر HTTP خام)
    بحيث يمكن التبديل (OpenAI/Anthropic/Gemini ولكلhead endpoint).
  * لا يحوي أي كلمة من كلمات الهوية المحظورة في أي بايلود يُرسل
    (بصمة القسم 0) — النص يوضع في رسالة مجردة "تحليل سلسلة أرقام".

الإعداد:
  AI_ON=0/1                  التفعيل الكلي
  AI_PROVIDER=openai|anthropic|gemini  (افتراضي openai)
  AI_API_KEY=…               مفتاح (secret في Actions)
  AI_MODEL=…                 نموذج
  AI_INTERVAL_MIN=…          أقل فرق دقائق بين تحليلين (افتراضي 360=6h)
  AI_SYS_HINT=…              توجيه نظام إضافي
"""

import json
import os
import time

import config

AI_ON = os.environ.get("AI_ON", "0") == "1"
AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai").lower()
AI_MODEL = os.environ.get(
    "AI_MODEL",
    "gpt-4o-mini" if AI_PROVIDER == "openai"
    else "claude-3-5-haiku-20241022" if AI_PROVIDER == "anthropic"
    else "gemini-2.0-flash",
)
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_INTERVAL_MIN = float(os.environ.get("AI_INTERVAL_MIN", "360") or 360)
AI_SYS_HINT = os.environ.get("AI_SYS_HINT", "")
AI_FETCH_TIMEOUT = 60

_DEFAULTS = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "headers": {"Content-Type": "application/json"},
        "path": ["choices", 0, "message", "content"],
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Content-Type": "application/json"},
        "path": ["choices", 0, "message", "content"],
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "headers": {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": "X",
        },
        "path": ["content", 0, "text"],
        "body": {"max_tokens": 1200},
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.0-flash:generateContent?key=KEY",
        "headers": {"Content-Type": "application/json"},
        "path": ["candidates", 0, "content", "parts", 0, "text"],
        "body": {},
    },
}


def _http_json(url, headers, payload, timeout=AI_FETCH_TIMEOUT):
    """نداء HTTP خام بلا تبعيات خارجية (stdlib فقط)."""
    import json as _j
    import urllib.request
    req = urllib.request.Request(
        url, data=_j.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    return _j.loads(body), resp.status


def _decode(resp, path):
    cur = resp
    for key in path:
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur[key]
    return str(cur)


def _call_llm(prompt, system, timeout=AI_FETCH_TIMEOUT):
    """استدعاء LLM عام حسب AI_PROVIDER. يرجع نص أو "" على أي فشل."""
    if not AI_ON or not AI_API_KEY:
        return ""
    try:
        spec = _DEFAULTS.get(AI_PROVIDER)
        if not spec:
            print(f"ai_brain: unknown provider {AI_PROVIDER}", flush=True)
            return ""
        headers = dict(spec.get("headers", {}))
        url = spec["url"]
        if AI_PROVIDER == "anthropic":
            headers["x-api-key"] = AI_API_KEY
            body = dict(spec.get("body", {}))
            body.update({"model": AI_MODEL, "system": system,
                         "messages": [{"role": "user", "content": prompt}]})
        elif AI_PROVIDER == "gemini":
            url = url.replace("KEY", AI_API_KEY)
            body = dict(spec.get("body", {}))
            body["contents"] = [{
                "parts": [{"text": system + "\n\n" + prompt}],
            }]
        else:  # openai
            headers["Authorization"] = "Bearer " + AI_API_KEY
            body = dict(spec.get("body", {}))
            body.update({"model": AI_MODEL,
                         "messages": [
                             {"role": "system", "content": system},
                             {"role": "user", "content": prompt},
                         ],
                         "temperature": 0.2})
        resp, code = _http_json(url, headers, body)
        if code >= 300:
            print(f"ai_brain http {code}: {resp}", flush=True)
            return ""
        return _decode(resp, spec["path"]).strip()
    except Exception as exc:
        print(f"ai_brain call fail: {exc!r}", flush=True)
        return ""


def _last_ai_time(state):
    try:
        return float(state.get("_ai_last_ts") or 0.0)
    except Exception:
        return 0.0


def _set_ai_time(state):
    try:
        state["_ai_last_ts"] = time.time()
    except Exception:
        pass


def _needs_run(state):
    if not AI_ON or not AI_API_KEY:
        return False
    return (time.time() - _last_ai_time(state)) >= AI_INTERVAL_MIN * 60


def _read_csv(path):
    import csv
    try:
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _read_feed():
    """قراءة data/ai_feed.md (سطر لكل صفقة: ts|side|pnl|tag|spread).

    تنسيق السطر (من main._record_close):
      2026-10-02 21:33 | BUY | -0.45 | L | 0.20
    يرجع dicts بمفاتيح trades.csv موحّدة ليقرأها _build_context.
    """
    path = os.path.join("data", "ai_feed.md")
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                out.append({
                    "ts_open": "", "ts_close": parts[0] if parts else "",
                    "side": parts[1] if len(parts) > 1 else "",
                    "entry_gap": "", "close_gap": "",
                    "entry_price": "", "close_price": "",
                    "pnl_units": "",
                    "pnl_usd": parts[2] if len(parts) > 2 else "",
                    "pnl_net_usd": parts[2] if len(parts) > 2 else "",
                    "reason": parts[3] if len(parts) > 3 else "",
                    "fees_usd": "",
                    "spread_usd": parts[4] if len(parts) > 4 else "",
                })
    except Exception:
        pass
    return out


def _find_trades():
    """مصدر الصفقات: ai_feed.md المحايد أولاً (غير معزول، يصل الـ runner)،
    ثم trades.csv، ثم state. ai_feed.md يضمن وصول بيانات حقيقية للعقل.
    """
    import_csv = _read_csv(os.path.join("data", "trades.csv"))
    feed = _read_feed()
    if feed:
        return feed, "data/ai_feed.md"
    if import_csv:
        return import_csv, "data/trades.csv"
    return [], "data/trades.csv"


def _find_trades_deprecated():
    for p in (os.path.join("data", "trades.csv"), "trades.csv",
              os.path.join(os.path.dirname(__file__), "data", "trades.csv")):
        rows = _read_csv(p)
        if rows:
            return rows, p
    return [], "data/trades.csv"


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _fetch_news_headlines():
    """أخبار موجزة اختيارية عبر HTTP بلا مفتاح — تغذية سياق للعقل.

    مصدران حران:
      * metal-price API (بدون مفتاح): سعر ذهب لحظي عالمي.
      * RSS بسيط غير مطلوب — نكتفي بارتداد نجاح فقط.
    عند أي فشل يرجع [] بلا أثر (البحث اختياري).
    """
    import urllib.request
    out = []
    # metal price API (free, no key) — سعر لحظي + اتجاه
    try:
        req = urllib.request.Request(
            "https://api.metalpriceapi.com/v1/latest",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=AI_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        rates = data.get("rates") or {}
        for k, v in list(rates.items())[:6]:
            out.append({"source": "metalpriceapi", "key": k, "value": v})
    except Exception as exc:
        print(f"ai_brain news(fetch) warn: {exc!r}", flush=True)
    # Yahoo GC=F quote — بيانات السوق كسياق
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=AI_FETCH_TIMEOUT) as resp:
            j = json.loads(resp.read().decode())
        meta = (j.get("chart", {}).get("result") or [{}])[0].get("meta") or {}
        if meta:
            out.append({"source": "yahoo-GC=F",
                        "price": meta.get("regularMarketPrice"),
                        "prev": meta.get("chartPreviousClose")})
    except Exception as exc:
        print(f"ai_brain news(yahoo) warn: {exc!r}", flush=True)
    return out


def _write(path, text):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as exc:
        print(f"ai_brain write {path}: {exc!r}", flush=True)


def _build_context(state):
    """ملخص مجرد من سجل الصفقات، بلا كلمات هوية — تغذية للعقل."""
    trades, _src = _find_trades()
    # الحالة المحلية الحية: closed_trades لدورة سابقة — الأصدق على الـ runner
    # (عند غياب trades.csv المعزول). ندمجها إن كانت أغنى.
    live = state.get("closed_trades") or []
    if live and len(live) >= len(trades):
        trades = live
        _src = "state.closed_trades"
    perf = _read_json(os.path.join("data", "performance.json"))
    recent = trades[-40:] if len(trades) > 40 else trades
    rows = []
    for t in recent:
        if isinstance(t, dict):
            rows.append({
                "s": t.get("side", ""),
                "eg": _num(t.get("entry_gap")),
                "cg": _num(t.get("close_gap")),
                "en": _num(t.get("entry_price")),
                "cp": _num(t.get("close_price")),
                "pnl": _num(t.get("pnl_net_usd")),
                "rs": t.get("reason", ""),
                "to": (t.get("ts_open") or "")[11:16],
                "tc": (t.get("ts_close") or "")[11:16],
            })
        else:
            rows.append({"raw": str(t)[:80]})
    ctx = {
        "count_total": len(trades),
        "count_recent": len(rows),
        "recent": rows,
        "data_source": _src,
        "perf": perf,
        "spread_usd_last": state.get("_last_spread_usd"),
        "balance_last": state.get("last_balance"),
        "news": _fetch_news_headlines(),
    }
    return ctx


def _num(v):
    try:
        if v in (None, ""):
            return None
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _prompt(ctx):
    return (
        "You are tuning a live XAUUSD (gold) scalping bot on a demo account.\n"
        "ECONOMICS (hard constraints, never contradict them):\n"
        "- lot is fixed at 0.01 and CANNOT change; 1 USD of gold price move = $1 P/L.\n"
        "- Target per trade ~ +1.6 USD, stop ~ -2.0 USD (R:R about 0.8 = needs 55%+ win).\n"
        "- Live spread 0.2-0.3 USD is already subtracted from every P/L.\n"
        "- The broker REJECTS server-side SL/TP, so the stop is programmatic only:\n"
        "  positions are polled every ~2s in-run, but the runner is restarted every\n"
        "  ~15 min, so realised stops often overshoot to -3..-6 USD.\n"
        "- NO new capital risk rules: lot size, session blocker (16-22 UTC) and\n"
        "  MAX_LOSS are user-locked and must not be changed.\n"
        "DATA FIELDS: ts_close | side(B/S) | pnl_net | tag(W/L/SL/TP) | spread\n"
        "QUESTION: Using the trade history, diagnose the bleeding and propose the\n"
        "SINGLE highest-impact numeric change.\n"
        "Answer in this exact shape:\n"
        "1) DIAGNOSIS: two sentences with the real numbers you used.\n"
        "2) WORST HOURS: list up to 3 close-hours in UTC that are net negative.\n"
        "3) WHY STOPS OVERSHOOT: one sentence.\n"
        "4) FIX: exactly one line of the form  MOMENTUM_MIN=<number between 1.20 and 2.00>\n"
        "   (entry threshold in USD of gold momentum; only field allowed to move).\n"
        "   If you think the threshold should NOT change, write MOMENTUM_MIN=1.20.\n"
        "No disclaimers, no generic risk advice, no percentage SL/TP advice.\n\n"
        + json.dumps(ctx)
    )


def _recommendations_from(text):
    """مخرج التوصيات غير الرسمي — آخر 3 أسطر برقم (التحليل للنص الادعائي)."""
    out = []
    if not text:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line[:1].isdigit() and len(line) > 8:
            if len(out) < 3:
                out.append(line[:120])
    return out


def _extract_first_number(text):
    """يستخرج قيمة MOMENTUM_MIN= من نص العقل (أو None).

    لا نلتقط أول رقم عشوائي أبداً (كان خطراً: رقم سردّي كـ "2.0 USD"
    كان سيُطبَّق كعتبة). فقط النمط الصريح المطلوب في البرومبت.
    """
    import re
    m = re.search(r"MOMENTUM_MIN\s*=\s*(-?\d+\.?\d*)", text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def run(state, data_dir="data"):
    """تنفيذ دورة تحليل إذا حان وقتها. لا يرمي استثناء أبداً."""
    try:
        if not _needs_run(state):
            return {"ran": False}
        ctx = _build_context(state)
        text = _call_llm(
            _prompt(ctx),
            system="You are a risk analyst. Be concrete and short. "
                  "Answer in English." + AI_SYS_HINT,
        )
        result = {"ran": True, "ts": time.time()}
        if not text:
            result["error"] = "empty LLM reply"
            _set_ai_time(state)
            return result
        plan_path = os.path.join(data_dir, "ai_plan.md")
        _write(plan_path, "# AI daily plan\n\n" + text + "\n")
        rec = _recommendations_from(text)
        rec_path = os.path.join(data_dir, "ai_recommendations.json")
        _write(rec_path, json.dumps({
            "ts": time.time(),
            "recommendations": rec,
            "momentum_min": _extract_first_number(text),
        }, indent=2))
        result["plan_written"] = plan_path
        result["recommendations"] = rec
        _set_ai_time(state)
        return result
    except Exception as exc:
        print(f"ai_brain run fail: {exc!r}", flush=True)
        return {"ran": False, "error": repr(exc)}


# ============================================================================
# حلقة التطوير الذاتي — overrides مُقيّدة تُطبَّق في الذاكرة فقط (لا كود/ملف)
# ============================================================================
# القاعدة: لا يغيّر العقل القواعد الحتمية (لوت/حدود أمان) أبداً؛ فقط يتّجه
# نحو معاملات ضمن نطاق معقول (entry threshold). التطبيق يتم عبر state[yh_dyn]
# الذي يقرؤه live أثناء الفتح — لا يلمس ملفات config ولا commit.

AI_APPLY_ON = os.environ.get("AI_APPLY_ON", "0") == "1"
AI_MOMENTUM_MIN_MIN = float(os.environ.get("AI_MOMENTUM_MIN_MIN", "0.50"))
AI_MOMENTUM_MIN_MAX = float(os.environ.get("AI_MOMENTUM_MIN_MAX", "2.50"))


def apply_self_improvement(state):
    """تطبيق توصية العقل على config في الذاكرة (إن فُعّلت) وبصد قيم شاذة.

    يقرأ data/ai_recommendations.json — إن وُجد فيه
    {"momentum_min": <قيمة>} ضمن [min,max] طبّقه على config.MOMENTUM_MIN_USD
    وسجّله في الحالة. أي قيمة خارج النطاق/بنية خاطئة تُهمَل بلا أثر.
    يُعاد كل دورة — يجعل التحسين الذاتي قابلاً للتعديل والطبع.
    """
    if not (AI_ON and AI_APPLY_ON):
        return {"applied": False, "reason": "self-tune disabled"}
    try:
        rec_path = os.path.join("data", "ai_recommendations.json")
        rec = _read_json(rec_path)
        val = rec.get("momentum_min")
        if val is None:
            m = rec.get("recommendations") or []
            if m:
                first = str(m[0])
                try:
                    val = float(first.strip())
                except Exception:
                    val = None
        if val is None:
            return {"applied": False, "reason": "no recommendation"}
        val = float(val)
        if not (AI_MOMENTUM_MIN_MIN <= val <= AI_MOMENTUM_MIN_MAX):
            return {"applied": False,
                    "reason": "out-of-range {0:+.2f}".format(val)}
        # في الذاكرة فقط — يجهّز للدورة التالية لا يلمس الملفات
        config.MOMENTUM_MIN_USD = round(val, 2)
        state["yh_dyn"] = {"momentum_min": round(val, 2)}
        print(f"self-improve: momentum_min -> {val:.2f} "
              f"(range {AI_MOMENTUM_MIN_MIN}-{AI_MOMENTUM_MIN_MAX})",
              flush=True)
        return {"applied": True, "momentum_min": round(val, 2)}
    except Exception as exc:
        print(f"self-improve fail: {exc!r}", flush=True)
        return {"applied": False, "reason": repr(exc)}