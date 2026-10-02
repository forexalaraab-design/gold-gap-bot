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
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as exc:
        print(f"ai_brain write {path}: {exc!r}", flush=True)


def _build_context(state):
    """ملخص مجرد من سجل الصفقات، بلا كلمات هوية — تغذية للعقل."""
    trades = _read_csv(os.path.join("data", "trades.csv"))
    perf = _read_json(os.path.join("data", "performance.json"))
    recent = trades[-40:] if len(trades) > 40 else trades
    rows = []
    for t in recent:
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
    ctx = {
        "count_total": len(trades),
        "count_recent": len(rows),
        "recent": rows,
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
    return ("Analyze this trading performance stream (XAUUSD demo). "
            "Give a SHORT diagnosis: which hours are losing, typical loss vs "
            "win shape, whether the strategy is net-negative and why, and 2-3 "
            "concrete numeric recommendations (entry threshold, time filter, "
            "SL/TP). Keep under 250 words.\n\n" + json.dumps(ctx))


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
    """أول رقم عشري في النص (يُستخدم كـ momentum_min المقترح) أو None."""
    import re
    m = re.search(r"-?\d+\.?\d*", text or "")
    if not m:
        return None
    try:
        return float(m.group(0))
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