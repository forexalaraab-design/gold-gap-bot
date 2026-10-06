# -*- coding: utf-8 -*-
"""
ai_brain.py â€” ط¹ظ‚ظ„ LLM ط®ط§ط±ط¬ظٹ ظ„ظ„ط¨ظˆطھ: ظٹط¨ط­ط« ظˆظٹط­ظ„ظ„ ظˆظٹط®ط·ط· (ظ…ط¹ ط¨ظˆط§ط¨ط© طھظ†ظپظٹط° ظ…ظ‚ظٹط¯ط©).

ط§ظ„ط؛ط±ط¶ (2026-10-02): ط§ظ„ظ…ط±ظƒط² ط§ظ„ط°ظٹ ظٹظپظƒط± ظپظˆظ‚ ط¨ظٹط§ظ†ط§طھ ط§ظ„ط¨ظˆطھ:
  * ظٹط¨ط­ط« ظپظٹ ط§ظ„ظˆظٹط¨ (ط£ط®ط¨ط§ط± ط§ظ„ط°ظ‡ط¨ / GC=F / ط¯ظˆط§ظپط¹ ط§ظ„ط³ظˆظ‚).
  * ظٹظ‚ط±ط£ ط³ط¬ظ„ ط§ظ„طµظپظ‚ط§طھ (trades.csv) + ط§ظ„ط£ط¯ط§ط، (performance.json) + ط§ظ„ط­ط§ظ„ط©.
  * ظٹط­ظ„ظ„ ط§ظ„ط³ط¨ط¨ظٹط© (ط§ظ„ط³ط§ط¹ط§طھ/ط§ظ„ط§طھط¬ط§ظ‡/ط§ظ„ط³طھظˆط¨ط§طھ/ط§ظ„ط±ط¨ط­) ظˆظٹط³طھظ†طھط¬ ظ‚ط±ط§ط±ط§ظ‹.
  * ظٹظƒطھط¨ "ط®ط·ط©" ظٹظˆظ…ظٹط© ظ…ظ‚ط±ظˆط،ط© ظپظٹ data/ai_plan.md.
  * ظٹظ†طھط¬ طھظˆطµظٹط§طھ ظ‚ط§ط¨ظ„ط© ظ„ظ„طھظ…ط«ظٹظ„ (طھط¹ط¯ظٹظ„ ط¹طھط¨ط©) ظپظٹ data/ai_recommendations.json
    ظ„ظٹظ‚ط±ط±ظ‡ط§ ط§ظ„ظ…ط³طھط®ط¯ظ… طµط±ط§ط­ط©ظ‹ â€” ظ„ط§ ظٹظڈظ†ظپظژظ‘ط° ط´ظٹط، طھظ„ظ‚ط§ط¦ظٹط§ظ‹ ظ…ظ† ط؛ظٹط± ظ…ظˆط§ظپظ‚ط©.

ط§ظ„ط¨ظ†ظٹط©:
  * ظ„ط§ ظٹطھطµظ„ ط¨ط§ظ„ط¨ط±ظˆظƒط± ط¥ط·ظ„ط§ظ‚ط§ظ‹ (ظ„ط§ ظ…ط¹ظ„ظˆظ…ط© ظ…ظ† ظپطھط­/ط¥ط؛ظ„ط§ظ‚ طھظڈط±ط³ظژظ„ ط¥ظ„ط§ ط¨ظٹط§ظ†ط§طھ ظ…ط¬ظ‡ظˆظ„ط©).
  * ظ„ط§ ظٹظ„ظ…ط³ state/live cycle â€” ظپظ‚ط· read + ظƒطھط§ط¨ط© ط£ظ‡ط¯ط§ظپ ظپظٹ data/.
  * ط£ظٹ ط§ط³طھط¯ط¹ط§ط، ظˆط®ط§ط±ط¬ظٹ ظٹظƒظˆظ† ط¹ط¨ط± AI_FETCH_TIMEOUT ظˆظٹطµظ…طھ ط¹ظ†ط¯ ط§ظ„ظپط´ظ„ (ظ„ط§ طھظˆظ‚ظپ)
    ط­طھظ‰ ظ„ظˆ ط؛ط§ط¨ ط§ظ„ظ…ظپطھط§ط­/ط§ظ„ط´ط¨ظƒط©.
  * ط§ظ„ظ…ط²ظˆط¯ ظ…طھظˆط§ظپظ‚ ظ…ط¹ OpenAI oembedded (chat/completions ط¹ط¨ط± HTTP ط®ط§ظ…)
    ط¨ط­ظٹط« ظٹظ…ظƒظ† ط§ظ„طھط¨ط¯ظٹظ„ (OpenAI/Anthropic/Gemini ظˆظ„ظƒظ„head endpoint).
  * ظ„ط§ ظٹط­ظˆظٹ ط£ظٹ ظƒظ„ظ…ط© ظ…ظ† ظƒظ„ظ…ط§طھ ط§ظ„ظ‡ظˆظٹط© ط§ظ„ظ…ط­ط¸ظˆط±ط© ظپظٹ ط£ظٹ ط¨ط§ظٹظ„ظˆط¯ ظٹظڈط±ط³ظ„
    (ط¨طµظ…ط© ط§ظ„ظ‚ط³ظ… 0) â€” ط§ظ„ظ†طµ ظٹظˆط¶ط¹ ظپظٹ ط±ط³ط§ظ„ط© ظ…ط¬ط±ط¯ط© "طھط­ظ„ظٹظ„ ط³ظ„ط³ظ„ط© ط£ط±ظ‚ط§ظ…".

ط§ظ„ط¥ط¹ط¯ط§ط¯:
  AI_ON=0/1                  ط§ظ„طھظپط¹ظٹظ„ ط§ظ„ظƒظ„ظٹ
  AI_PROVIDER=openai|anthropic|gemini  (ط§ظپطھط±ط§ط¶ظٹ openai)
  AI_API_KEY=â€¦               ظ…ظپطھط§ط­ (secret ظپظٹ Actions)
  AI_MODEL=â€¦                 ظ†ظ…ظˆط°ط¬
  AI_INTERVAL_MIN=â€¦          ط£ظ‚ظ„ ظپط±ظ‚ ط¯ظ‚ط§ط¦ظ‚ ط¨ظٹظ† طھط­ظ„ظٹظ„ظٹظ† (ط§ظپطھط±ط§ط¶ظٹ 360=6h)
  AI_SYS_HINT=â€¦              طھظˆط¬ظٹظ‡ ظ†ط¸ط§ظ… ط¥ط¶ط§ظپظٹ
"""

import json
import os
import time

import config
import ai_lab as _lab

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
    """ظ†ط¯ط§ط، HTTP ط®ط§ظ… ط¨ظ„ط§ طھط¨ط¹ظٹط§طھ ط®ط§ط±ط¬ظٹط© (stdlib ظپظ‚ط·)."""
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
    """ط§ط³طھط¯ط¹ط§ط، LLM ط¹ط§ظ… ط­ط³ط¨ AI_PROVIDER. ظٹط±ط¬ط¹ ظ†طµ ط£ظˆ "" ط¹ظ„ظ‰ ط£ظٹ ظپط´ظ„."""
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


# ط·ط§ط¨ط¹ ط¢ط®ط± طھط´ط؛ظٹظ„: ظ…ظ„ظپ ط¯ط§ط¦ظ… ظپظٹ data/ (ط؛ظٹط± ظ…ط¹ط²ظˆظ„ â€” ظٹظڈط±ظپط¹ ظ…ط¹ persist)طŒ ظ„ط£ظ†
# state (bot_state.json) ظ…ط¹ط²ظˆظ„ ظˆظ„ط§ ظٹطµظ„ ط¨ظٹظ† ط§ظ„ط¯ظˆط±ط§طھ â‡’ ظ„ظˆ ط§ظƒطھظپظٹظ†ط§ ط¨ظ‡ ظ„ط¨ظ‚ظٹ
# ط§ظ„طµظپط± ظƒظ„ ط¯ظˆط±ط© ظپظ†رˆذ°ذ» ط¹ظ„ظ‰ "ظƒظ„ ط¯ظˆط±ط©" ط¨ط¯ظ„ AI_INTERVAL_MIN. txt ظ…ط­ط§ظٹط¯ ط¨ظ„ط§ ظ‡ظˆظٹط©.
_STAMP_FILE = os.path.join("data", "ai_last_run.txt")


def _last_ai_time(state):
    try:
        v = float(state.get("_ai_last_ts") or 0.0)
        if v > 0:
            return v
    except Exception:
        pass
    try:
        with open(_STAMP_FILE, "r", encoding="utf-8") as f:
            return float((f.read() or "0").strip() or 0.0)
    except Exception:
        return 0.0


def _set_ai_time(state):
    now = time.time()
    try:
        state["_ai_last_ts"] = now
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(_STAMP_FILE), exist_ok=True)
        with open(_STAMP_FILE, "w", encoding="utf-8") as f:
            f.write(str(now))
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
    """ظ‚ط±ط§ط،ط© data/ai_feed.md (ط³ط·ط± ظ„ظƒظ„ طµظپظ‚ط©: ts|side|pnl|tag|spread).

    طھظ†ط³ظٹظ‚ ط§ظ„ط³ط·ط± (ظ…ظ† main._record_close):
      2026-10-02 21:33 | BUY | -0.45 | L | 0.20
    ظٹط±ط¬ط¹ dicts ط¨ظ…ظپط§طھظٹط­ trades.csv ظ…ظˆط­ظ‘ط¯ط© ظ„ظٹظ‚ط±ط£ظ‡ط§ _build_context.
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
    """ظ…طµط¯ط± ط§ظ„طµظپظ‚ط§طھ: ai_feed.md ط§ظ„ظ…ط­ط§ظٹط¯ ط£ظˆظ„ط§ظ‹ (ط؛ظٹط± ظ…ط¹ط²ظˆظ„طŒ ظٹطµظ„ ط§ظ„ظ€ runner)طŒ
    ط«ظ… trades.csvطŒ ط«ظ… state. ai_feed.md ظٹط¶ظ…ظ† ظˆطµظˆظ„ ط¨ظٹط§ظ†ط§طھ ط­ظ‚ظٹظ‚ظٹط© ظ„ظ„ط¹ظ‚ظ„.
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


def _journal_tail(n=40):
    """آخر أسطر سجل قرارات العقل — تغذية مغلقة (يتعلم من نتائجه السابقة)."""
    try:
        with open(AI_JOURNAL, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[-n:])[-2500:]
    except Exception:
        return ""


def _fetch_web_context():
    """بحث إنترنت حقيقي بلا مفتاح: أخبار ذهب/دولار/ECB من RSS.

    rss محايد بلا هوية. أي فشل ⇒ [] (لا يوقف العقل).
    """
    import urllib.request
    import re as _re
    feeds = [
        ("cnbc-gold", "https://search.cnbc.com/rs/search/combinedcms/view.xml"
         "?partnerId=wrss01&id=20910258"),
        ("yahoo-gold", "https://feeds.finance.yahoo.com/rss/2.0/headline"
         "?s=GC=F&region=US&lang=en-US"),
        ("marketwatch-top", "https://feeds.content.dowjones.io/public/rss"
         "/mw_topstories"),
    ]
    out = []
    for name, url in feeds:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml = resp.read().decode("utf-8", "ignore")
            titles = _re.findall(r"<title>(.*?)</title>", xml, _re.S)[:6]
            for t in titles:
                t = _re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t)
                t = _re.sub(r"<[^>]+>", "", t).strip()
                if t and len(t) > 8:
                    out.append({"src": name, "headline": t[:150]})
        except Exception as exc:
            print("web({0}) warn: {1!r}".format(name, exc), flush=True)
    return out[:12]


def _fetch_news_headlines():
    """ط£ط®ط¨ط§ط± ظ…ظˆط¬ط²ط© ط§ط®طھظٹط§ط±ظٹط© ط¹ط¨ط± HTTP ط¨ظ„ط§ ظ…ظپطھط§ط­ â€” طھط؛ط°ظٹط© ط³ظٹط§ظ‚ ظ„ظ„ط¹ظ‚ظ„.

    ظ…طµط¯ط±ط§ظ† ط­ط±ط§ظ†:
      * metal-price API (ط¨ط¯ظˆظ† ظ…ظپطھط§ط­): ط³ط¹ط± ط°ظ‡ط¨ ظ„ط­ط¸ظٹ ط¹ط§ظ„ظ…ظٹ.
      * RSS ط¨ط³ظٹط· ط؛ظٹط± ظ…ط·ظ„ظˆط¨ â€” ظ†ظƒطھظپظٹ ط¨ط§ط±طھط¯ط§ط¯ ظ†ط¬ط§ط­ ظپظ‚ط·.
    ط¹ظ†ط¯ ط£ظٹ ظپط´ظ„ ظٹط±ط¬ط¹ [] ط¨ظ„ط§ ط£ط«ط± (ط§ظ„ط¨ط­ط« ط§ط®طھظٹط§ط±ظٹ).
    """
    import urllib.request
    out = []
    # metal price API (free, no key) â€” ط³ط¹ط± ظ„ط­ط¸ظٹ + ط§طھط¬ط§ظ‡
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
    # Yahoo GC=F quote â€” ط¨ظٹط§ظ†ط§طھ ط§ظ„ط³ظˆظ‚ ظƒط³ظٹط§ظ‚
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
    """ظ…ظ„ط®طµ ظ…ط¬ط±ط¯ ظ…ظ† ط³ط¬ظ„ ط§ظ„طµظپظ‚ط§طھطŒ ط¨ظ„ط§ ظƒظ„ظ…ط§طھ ظ‡ظˆظٹط© â€” طھط؛ط°ظٹط© ظ„ظ„ط¹ظ‚ظ„."""
    trades, _src = _find_trades()
    # ط§ظ„ط­ط§ظ„ط© ط§ظ„ظ…ط­ظ„ظٹط© ط§ظ„ط­ظٹط©: closed_trades ظ„ط¯ظˆط±ط© ط³ط§ط¨ظ‚ط© â€” ط§ظ„ط£طµط¯ظ‚ ط¹ظ„ظ‰ ط§ظ„ظ€ runner
    # (ط¹ظ†ط¯ ط؛ظٹط§ط¨ trades.csv ط§ظ„ظ…ط¹ط²ظˆظ„). ظ†ط¯ظ…ط¬ظ‡ط§ ط¥ظ† ظƒط§ظ†طھ ط£ط؛ظ†ظ‰.
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
    # إحصاء كل ساعة على كامل السجل (لا آخر 40 فقط) — أساس قرار ساعات
    # التداول. hour -> [عدد, صافي, فوز]
    hour_stats = {}
    for t in trades:
        if not isinstance(t, dict):
            continue
        ts = (t.get("ts_close") or "")[11:13]
        if not ts.isdigit():
            continue
        pnl = _num(t.get("pnl_net_usd"))
        if pnl is None:
            continue
        rec = hour_stats.setdefault(int(ts), [0, 0.0, 0])
        rec[0] += 1
        rec[1] = round(rec[1] + pnl, 2)
        if pnl > 0:
            rec[2] += 1
    hours = [{"h": h, "n": v[0], "net": v[1],
              "win%": round(100.0 * v[2] / v[0], 1) if v[0] else 0}
             for h, v in sorted(hour_stats.items())]
    # حسب سبب الإغلاق — يعرف أين تتسرّب الخسارة فعلياً
    reason_stats = {}
    for t in trades:
        if not isinstance(t, dict):
            continue
        rs = (t.get("reason") or "?").strip()
        pnl = _num(t.get("pnl_net_usd"))
        if pnl is None:
            continue
        agg = reason_stats.setdefault(rs, [0, 0.0, 0])
        agg[0] += 1
        agg[1] = round(agg[1] + pnl, 2)
        if pnl > 0:
            agg[2] += 1
    reasons = [{"reason": k, "n": v[0], "net": v[1],
                "win%": round(100.0 * v[2] / v[0], 1) if v[0] else 0}
               for k, v in sorted(reason_stats.items(), key=lambda x: x[1][1])]
    ctx = {
        "count_total": len(trades),
        "count_recent": len(rows),
        "recent": rows,
        "data_source": _src,
        "perf": perf,
        "hour_stats_all": hours,
        "reason_stats_all": reasons,
        "params_in_force": state.get("ai_applied") or {},
        "own_journal_tail": _journal_tail(),
        "spread_usd_last": state.get("_last_spread_usd"),
        "balance_last": state.get("last_balance"),
        "news": _fetch_news_headlines(),
        "web_research": _fetch_web_context(),
        "backtest_baseline": _current_params_metrics(),
        "backtest_candidates": _measured_candidates(),
        "lessons_learned": _lab.knowledge_tail(30),
        "professionalism": _lab.professionalism(),
        "high_impact_events_utc": _upcoming_events(),
    }
    return ctx


def _current_params_metrics():
    """مقاييس الاختبار الخلفي للمعاملات الحيّة الحالية = خط الأساس.

    يُقارن بها أي اقتراح جديد قبل تطبيقه.
    """
    try:
        cur = {
            "momentum_min": round(float(config.MOMENTUM_MIN_USD), 2),
            "profit_target_usd": round(float(config.PROFIT_TARGET_USD), 2),
            "max_loss_usd": round(float(config.MAX_LOSS_USD), 2),
            "blocked_hours": sorted(
                getattr(config, "AI_BLOCKED_HOURS", None) or set()),
        }
        rows = _lab.load_history()
        if len(rows) < 30:
            return {"metrics": {}, "note": "history too small",
                    "sample": len(rows)}
        return {"params": cur, "sample": len(rows),
                "metrics": _lab.backtest(cur, rows)}
    except Exception as exc:
        print("baseline metrics warn: {0!r}".format(exc), flush=True)
        return {"metrics": {}}


def _measured_candidates():
    """خيارات مُقاسة على التاريخ (لا أرقام متخيّلة) — يختار منها العقل."""
    try:
        rows = _lab.load_history()
        if len(rows) < 30:
            return []
        base = _live_params()
        out = []
        for m in _lab.candidate_grid(rows, base_blocked=base["blocked_hours"]):
            out.append({
                "params": "momentum_min={0}, profit_target_usd={1}, "
                          "max_loss_usd={2}".format(
                              m["params"]["momentum_min"],
                              m["params"]["profit_target_usd"],
                              m["params"]["max_loss_usd"]),
                "n": m["n"], "net": m["net"], "win_rate": m["win_rate"],
                "payoff": m["payoff"], "expectancy": m["expectancy"],
                "profit_factor": m["profit_factor"],
            })
        return out
    except Exception as exc:
        print("candidates warn: {0!r}".format(exc), flush=True)
        return []


def _upcoming_events(days=3):
    """أحداث USD عالية التأثير القادمة (NFP/CPI/FOMC) بصيغة نصية."""
    try:
        evs = _lab.fetch_calendar()
        return evs[:days * 3]
    except Exception:
        return []


def _num(v):
    try:
        if v in (None, ""):
            return None
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _prompt(ctx):
    return (
        "You are the tuning brain of a live XAUUSD (gold) scalp bot. You have\n"
        "FULL AUTHORITY to retune it every hour, applied automatically without\n"
        "asking anyone. Aim: strong profit, near-zero bleed.\n"
        "ECONOMICS (never contradict):\n"
        "- lot is FIXED at 0.01 and can never change; $1 gold move = $1 P/L.\n"
        "- spread (0.04-0.30 USD) is already subtracted from every P/L.\n"
        "- entries fire when |platform_momentum - yahoo_momentum| >= momentum_min.\n"
        "- the stop is PROGRAMMATIC only (broker rejects server SL/TP), polled\n"
        "  ~2s in-run, but the runner restarts ~15min, so stops overshoot -3..-6.\n"
        "YOUR LEVERS (you own all of these; each has a hard cage):\n"
        "  momentum_min       0.60-2.60  entry threshold in USD\n"
        "  profit_target_usd  0.80-6.00  take-profit per trade\n"
        "  trailing_arm_usd   0.50-5.00  trail starts at this net profit\n"
        "  trailing_back_usd  0.15-2.00  close if giveback from peak\n"
        "  max_loss_usd       0.80-2.50  hard stop ceiling (absolute 2.50)\n"
        "  sl_after_entry_usd 0.80-2.50  protective stop after entry\n"
        "  cooldown_minutes   0.5-30.0   wait between trades\n"
        "  blocked_hours      up to 6 UTC hours (0-23, comma list) to stop trading\n"
        "  (values outside their range are REJECTED; the stop cannot exceed 2.50.)\n"
        "NEVER FREEZE TRADING: block ONLY hours that are NET NEGATIVE in the data.\n"
        "A profitable hour is never blocked, and at least 8 UTC hours must always\n"
        "stay tradeable. If unsure a hour is bad, do NOT block it. Omitting\n"
        "blocked_hours entirely releases every hour you blocked before.\n"
        "If a change makes recent results PROFITABLE, prefer loosening (lower\n"
        "momentum_min / lower stop) over freezing - never stop trading for good.\n"
        "THE PAYOFF TRAP: avg win vs avg loss decides survival. If payoff < 1.0,\n"
        "you MUST raise profit_target_usd and/or cut max_loss_usd, not just raise\n"
        "momentum_min. Raising the entry threshold alone just freezes trading.\n"
        "Use hour_stats_all to block the losing UTC hours, reason_stats_all to see\n"
        "where losses leak, web_research/news for market context, and\n"
        "own_journal_tail + params_in_force + lessons_learned to correct your\n"
        "OWN past mistakes. Never repeat a proposal that lessons_learned shows\n"
        "was REJECTED by the backtest.\n"
        "CHECK high_impact_events_utc (NFP/CPI/FOMC): real traders stand aside\n"
        "around those, so prefer tighter stops on such days, not frozen hours.\n"
        "backtest_candidates are REAL measured results on the full history, best\n"
        "first (net/win_rate/payoff/expectancy/profit_factor per option).\n"
        "backtest_baseline is what is live now, measured exactly the same way.\n"
        "RULES OF A PROFESSIONAL: take your numbers FROM backtest_candidates -\n"
        "never invent untested values. Prefer an option whose NEIGHBOURS in that\n"
        "list are also strong: that means robustness, not a lucky cell. If every\n"
        "option is worse than backtest_baseline, keep momentum_min unchanged.\n"
        "Your proposal is auto-backtested and DISCARDED if it fails to beat the\n"
        "live baseline, so only propose what those numbers can defend.\n"
        "REPLY IN THIS EXACT SHAPE:\n"
        "1) DIAGNOSIS: 2 sentences citing real numbers.\n"
        "2) WHAT YOU CHANGED VS LAST HOUR: one sentence.\n"
        "3) RISK: one sentence on the worst downside of your own change.\n"
        "4) PARAMS: a single line then a PARAMS block of key=value pairs, e.g.\n"
        "PARAMS:\n"
        "momentum_min=1.40\n"
        "profit_target_usd=2.40\n"
        "max_loss_usd=1.60\n"
        "blocked_hours=13,14,15\n"
        "Always give the full PARAMS block with your chosen values. Be concrete,\n"
        "quantitative and brief. No disclaimers, no generic advice.\n\n"
        + json.dumps(ctx)
    )


def _recommendations_from(text):
    """ظ…ط®ط±ط¬ ط§ظ„طھظˆطµظٹط§طھ ط؛ظٹط± ط§ظ„ط±ط³ظ…ظٹ â€” ط¢ط®ط± 3 ط£ط³ط·ط± ط¨ط±ظ‚ظ… (ط§ظ„طھط­ظ„ظٹظ„ ظ„ظ„ظ†طµ ط§ظ„ط§ط¯ط¹ط§ط¦ظٹ)."""
    out = []
    if not text:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line[:1].isdigit() and len(line) > 8:
            if len(out) < 3:
                out.append(line[:120])
    return out


def _critique_verdict(critique):
    """يستخرج حكم الناقد: VETO / APPROVE / None (إن لم يذكر)."""
    t = (critique or "").upper()
    if "VETO" in t:
        return "VETO"
    if "APPROVE" in t:
        return "APPROVE"
    return None


def _critique_prompt(ctx, first_pass):
    """نقد مستقل للقرار الأول (Pass 2) — عقل ناقد لا يوافق تلقائياً."""
    base = _current_params_metrics()
    return (
        "You are a SKEPTICAL risk manager reviewing another trader's hourly\n"
        "decision on a live XAUUSD bot. Your job is to find the flaw, not to\n"
        "agree. The proposal below is auto-backtested and is DISCARDED unless\n"
        "it beats the live baseline on expectancy, net, payoff and loss streak.\n"
        "FIRST PASS DECISION:\n" + (first_pass or "")[:1200] +
        "\n\nLIVE BASELINE (measured): " + json.dumps(base.get("metrics") or {}) +
        "\nMEASURED CANDIDATES (best first): " + json.dumps(
            ctx.get("backtest_candidates") or [])[:1200] +
        "\nEVENTS (high impact): " + json.dumps(
            ctx.get("high_impact_events_utc") or [])[:400] +
        "\n\nAnswer in exactly this shape:\n"
        "FLAW: one sentence naming the strongest objection to the proposal.\n"
        "OVERFIT_RISK: one sentence - is the pick a lone outlier or supported\n"
        "  by its neighbours in the measured list?\n"
        "VERDICT: exactly one of  APPROVE  /  VETO  then a reason.\n"
        "Keep it under 90 words. No disclaimers.\n"
    )


def _extract_first_number(text):
    """ظٹط³طھط®ط±ط¬ ظ‚ظٹظ…ط© MOMENTUM_MIN= ظ…ظ† ظ†طµ ط§ظ„ط¹ظ‚ظ„ (ط£ظˆ None).

    ظ„ط§ ظ†ظ„طھظ‚ط· ط£ظˆظ„ ط±ظ‚ظ… ط¹ط´ظˆط§ط¦ظٹ ط£ط¨ط¯ط§ظ‹ (ظƒط§ظ† ط®ط·ط±ط§ظ‹: ط±ظ‚ظ… ط³ط±ط¯ظ‘ظٹ ظƒظ€ "2.0 USD"
    ظƒط§ظ† ط³ظٹظڈط·ط¨ظژظ‘ظ‚ ظƒط¹طھط¨ط©). ظپظ‚ط· ط§ظ„ظ†ظ…ط· ط§ظ„طµط±ظٹط­ ط§ظ„ظ…ط·ظ„ظˆط¨ ظپظٹ ط§ظ„ط¨ط±ظˆظ…ط¨طھ.
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
    """طھظ†ظپظٹط° ط¯ظˆط±ط© طھط­ظ„ظٹظ„ ط¥ط°ط§ ط­ط§ظ† ظˆظ‚طھظ‡ط§. ظ„ط§ ظٹط±ظ…ظٹ ط§ط³طھط«ظ†ط§ط، ط£ط¨ط¯ط§ظ‹."""
    try:
        if not _needs_run(state):
            return {"ran": False}
        ctx = _build_context(state)
        text = _call_llm(
            _prompt(ctx),
            system="You are a risk analyst. Be concrete and short. "
                  "Answer in English." + AI_SYS_HINT,
        )
        # ---- مرحلة نقد:Pass 2. عقل ناقد مستقل يفحص第一条分析与 بوابة
        # الاختبار الخلفي قبل التنفيذ. هذا هو الفرق between "قرر" و"-trade
        # ما بعد تفكير". إن发现Pass 1 لا撑得住，则 we retain current.
        critique = ""
        if text:
            critique = _call_llm(
                _critique_prompt(ctx, text),
                system="You are a skeptical risk manager reviewing another "
                       "trader's decision. Find the flaw. Be brief." +
                       AI_SYS_HINT,
            ) or ""
            _lab.knowledge_append(
                "REVIEW pass1={0} | critic={1}".format(
                    _extract_first_number(text),
                    (critique or "n/a")[:220].replace("\n", " ")))
        result = {"ran": True, "ts": time.time(), "critique": critique[:400]}
        if not text:
            result["error"] = "empty LLM reply"
            _set_ai_time(state)
            return result
        # ط§ظ„ط±ظ‚ظ… ط§ظ„ظ…ظ†ظپظژظ‘ط° ظپظٹ ط³ط·ط± ظ…ط³طھظ‚ظ„ ط¯ط§ط®ظ„ ط§ظ„ط®ط·ط©: ط§ظ„ط®ط·ط© (.md) ط§ظ„ظ…ظ„ظپ
        # ط§ظ„ط¯ط§ط¦ظ… ط§ظ„ط°ظٹ ظٹطµظ„ ط§ظ„ط¯ظˆط±ط© ط§ظ„طھط§ظ„ظٹط©طŒ ط¨ظٹظ†ظ…ط§ json ظ…ط¹ط²ظˆظ„ ظˆظ„ط§ ظٹطµظ„.
        # الخطة (.md) هي الملف الدائم الذي تصل الدورة التالية. نكتب فيها
        # كتلة PARAMS المُطبَّقة صراحةً حتى لو garbled ردّ العقل، فيقرأها
        # apply_self_improvement مباشرة دون إعادة تحليل النص.
        params = _parse_param_block(text)
        for k, v in list(params.items()):
            if k == "blocked_hours":
                safe = _parse_blocked_hours(v)
            else:
                safe = _clamp_param(k, v)
            if safe is None:
                params.pop(k)
            else:
                params[k] = safe
        if not params:
            _mm = _extract_first_number(text)
            params = {"momentum_min": _mm} if _mm is not None else {}
        # ---- بوابة الاختبار: لا يُكتب إلا ما أثبت تفوّقه على التاريخ ----
        verdict, cand_m, base_m, verdict_note = _validate_params(params)
        rejected = verdict is not True
        # حكم الناقد (Pass 2): يعترض فقط إن كانت الأفضلية هامشية. أفضلية
        # كبيرة مُقاسة (مثلاً 0.40 مقابل -0.06) تتجاوز الاعتراض الشكلي؛
        # اعتراضٌ على تغييرٍ ضعيف الأثر = سبب كافٍ للاحتفاظ بالحيّ.
        cv = _critique_verdict(critique)
        margin = (float(cand_m.get("expectancy") or 0.0)
                  - float(base_m.get("expectancy") or 0.0))
        if (not rejected) and cv == "VETO" and margin < 0.10:
            rejected = True
            verdict_note = ("critic VETO with thin margin ({0:+.3f})".format(
                margin))
            params = _live_params()
            result["rejected_params"] = True
        result["critique_verdict"] = cv
        result["improvement_margin"] = round(margin, 3)
        result["backtest"] = {"candidate": cand_m, "baseline": base_m,
                              "verdict": verdict, "note": verdict_note}
        if rejected:
            _lab.knowledge_append(
                "REJECTED {0} -> {1}".format(
                    ",".join("{0}={1}".format(k, v)
                             for k, v in sorted(params.items())), verdict_note))
            print("backtest gate: REJECTED ({0}) -> keeping live params".format(
                verdict_note), flush=True)
            params = _live_params()
            result["rejected_params"] = True
        result["plan_written"] = os.path.join(data_dir, "ai_plan.md")
        header = "# AI plan  ({0} UTC)".format(
            time.strftime("%Y-%m-%d %H:%M", time.gmtime()))
        footer = "\n\n## APPLIED (auto-applied next cycle, hard-bounded)\n"
        if params:
            footer += "PARAMS:\n" + "\n".join(
                "{0}={1}".format(k, v) for k, v in sorted(params.items()))
        else:
            footer += "PARAMS: (none parsed — keeping current settings)"
        # دليل ساعات التداول: أرباح/خسائر كل ساعة UTC على كامل السجل.
        # يقرأه الحارس فلا يُحظر إلا ساعة خاسرة، ويُبقي جدول تداول مفتوح.
        hn = ctx.get("hour_stats_all") or []
        if hn:
            footer += "\nHOURNET: " + ", ".join(
                "{0}={1:+g}/{2}".format(x["h"], x["net"], x["n"]) for x in hn)
        footer += "\nBACKTEST_GATE: {0} | cand exp={1} baseline exp={2} | cand net={3} baseline net={4}".format(
            "PASS" if not rejected else "REJECTED: " + str(verdict_note),
            cand_m.get("expectancy"), base_m.get("expectancy"),
            cand_m.get("net"), base_m.get("net"))
        footer += "\nCRITIC(Pass2): {0} | improvement margin={1}".format(
            _critique_verdict(critique), round(margin, 3))
        _prof = ctx.get("professionalism") or {}
        footer += "\nPROFESSIONALISM: {0}/100 ({1})".format(
            _prof.get("score"), _prof.get("verdict"))
        try:
            gr = _lab.graduation_report()
            footer += "\nGRADUATION: {0}/{1} checks | {2} | live-account switch is MANUAL by design".format(
                gr["passed"], gr["total"], gr["verdict"])
        except Exception:
            pass
        _write(result["plan_written"], header + "\n\n" + text + footer + "\n")
        _write(os.path.join(data_dir, "ai_recommendations.json"),
               json.dumps({
                   "ts": time.time(),
                   "recommendations": _recommendations_from(text),
                   "params": params,
                   "momentum_min": params.get("momentum_min"),
               }, indent=2))
        result["params"] = params
        result["momentum_min"] = params.get("momentum_min")
        _set_ai_time(state)
        return result
    except Exception as exc:
        print(f"ai_brain run fail: {exc!r}", flush=True)
        return {"ran": False, "error": repr(exc)}


# ============================================================================
# ظ…ط­ط±ظ‘ظƒ ط§ظ„طھط·ط¨ظٹظ‚ ط§ظ„ط°ط§طھظٹ â€” ط³ظ„ط·ط§ظ† ظƒط§ظ…ظ„ ط¹ظ„ظ‰ ط§ظ„ظ…ط¹ط§ظ…ظ„ط§طھطŒ ط¨ظ‚ظپطµ ط­ط¯ظˆط¯ طµظ„ط¨ط©
# ============================================================================
# 2026-10-05 (ط·ظ„ط¨ طµط±ظٹط­): ط§ظ„ط¹ظ‚ظ„ ظ…ط®ظˆظ‘ظ„ ط¨ط§ظ„ظƒط§ظ…ظ„ ظ„طھط¹ط¯ظٹظ„ ط§ظ„ط¹طھط¨ط© ظˆط§ظ„ظ‡ط¯ظپ ظˆظˆظ‚ظپ
# ط§ظ„ط®ط³ط§ط±ط© ظˆط§ظ„طھط±ظٹظ„ظ†ط¬ ظˆط§ظ„طھظ‡ط¯ط¦ط© ظˆط³ط§ط¹ط§طھ ط§ظ„طھط¯ط§ظˆظ„طŒ ظˆظٹط¨ط­ط« ظپظٹ ط§ظ„ط¥ظ†طھط±ظ†طھ ظˆظٹطھط·ظˆط±
# ط°ط§طھظٹط§ظ‹طŒ ط¨ظ„ط§ ط±ط¬ظˆط¹ ظ„ط£ظٹ ظ…ظˆط§ظپظ‚ط©.
#
# ط§ظ„ظ‚ظپطµ ط؛ظٹط± ظ‚ط§ط¨ظ„ ظ„ظ„ط§ط®طھط±ط§ظ‚ (ط­طھظ‰ ظ„ظˆ hallucinate):
#   * config.AI_BOUNDS ظٹط­ط¯ظ‘ ظƒظ„ ظ‚ظٹظ…ط© (ط³ظ‚ظپ ط§ظ„ط³طھظˆط¨ ط§ظ„ظ…ط·ظ„ظ‚ AI_MAX_STOP_USD).
#   * ط§ظ„ظ„ظˆطھ 0.01 ط®ط§ط±ط¬ ظ‡ط°ط§ ط§ظ„ط¬ط¯ظˆظ„ ط¹ظ…ط¯ط§ظ‹ â‡’ ظ„ط§ طھظ…ط¯ظ‘ط¯ ط­ط¬ظ… ط£ط¨ط¯ط§ظ‹.
#   * ط§ظ„طھط·ط¨ظٹظ‚ ظپظٹ ط§ظ„ط°ط§ظƒط±ط© ظپظ‚ط·: ظ„ط§ ظٹظƒطھط¨ config ظˆظ„ط§ commit â‡’ طµظپط± ط®ط·ط± ظƒظˆط¯.
#   * ط£ظٹ ظ‚ظٹظ…ط© ظ…ظپظ‚ظˆط¯ط©/ط¹ط¨ط«ظٹط©/ط®ط§ط±ط¬ ط§ظ„ظ†ط·ط§ظ‚ طھظڈطھط¬ط§ظ‡ظ„è¯¥é،¹ ظپظ‚ط·طŒ ظˆط§ظ„ط¨ط§ظ‚ظٹ ظٹظڈط·ط¨ظژظ‘ظ‚.
#   * ظƒظ„ ط¶ط¨ط·ط© طھظڈط³ط¬ظژظ‘ظ„ ظپظٹ data/ai_journal.md ظ…ط¹ ط­طµظٹظ„طھظ‡ط§ â‡’ ط¯ظˆط±ط© طھط¹ظ„ظ‘ظ… ظ…ط؛ظ„ظ‚ط©:
#     ط§ظ„ط¹ظ‚ظ„ ظپظٹ ط¯ظˆط±طھظ‡ ط§ظ„طھط§ظ„ظٹط© ظٹظ‚ط±ط£ ظ…ط§ ظپط¹ظ„ظ‡ ظ‚ط¨ظ„ ط°ظ„ظƒ ظˆظٹطµط­ظ‘ط­.

AI_APPLY_ON = os.environ.get("AI_APPLY_ON", "0") == "1"
AI_JOURNAL = os.path.join("data", "ai_journal.md")

# ط§ط³ظ… ط§ظ„ظ…طھط؛ظٹظ‘ط± ظپظٹ config  <-  ط§ظ„ط§ط³ظ… ط§ظ„ط°ظٹ ظٹظƒطھط¨ظ‡ ط§ظ„ط¹ظ‚ظ„ ظپظٹ ظƒطھظ„ط© PARAMS
_PARAM_TARGETS = {
    "momentum_min": "MOMENTUM_MIN_USD",
    "profit_target_usd": "PROFIT_TARGET_USD",
    "trailing_arm_usd": "TRAILING_ARM_USD",
    "trailing_back_usd": "TRAILING_BACK_USD",
    "max_loss_usd": "MAX_LOSS_USD",
    "sl_after_entry_usd": "SL_AFTER_ENTRY_USD",
    "cooldown_minutes": "COOLDOWN_MINUTES",
}


def _clamp_param(key, raw):
    """ظٹط­ظˆظ‘ظ„ ظ‚ظٹظ…ط© ظ…ظ‚طھط±ط­ط© ط¥ظ„ظ‰ ظ‚ظٹظ…ط© ط¢ظ…ظ†ط© ط¶ظ…ظ† config.AI_BOUNDSطŒ ط£ظˆ None ط¥ظ† ط±ظپط¶.

    ظٹط±ظپط¶: ط؛ظٹط± ط±ظ‚ظ…ظٹطŒ NaN/infطŒ ط®ط§ط±ط¬ ط§ظ„ظ†ط·ط§ظ‚ (ظ„ط§ ظ‚طµظ‘ طµط§ظ…طھ â€” ظ†ظڈط¨ظ‚ظٹ ظ…طµط¯ط§ظ‚ظٹط© ط§ظ„ظˆطµظپط©).
    ظٹط­ط¯ظ‘ ط§ظ„ط³طھظˆط¨: ظ„ط§ ظٹطھط¬ط§ظˆط² AI_MAX_STOP_USDطŒ ظˆظ„ط§ ظٹظ‚ظپط² ط£ظƒط«ط± ظ…ظ† +0.10$ ظپظˆظ‚
    ط§ظ„ط­ط§ظ„ظٹ ط¯ظپط¹ط© ظˆط§ط­ط¯ط© (incremental safety â€” ظ„ط§ ظ‚ظپط²ط§طھ ظ…ظپط§ط¬ط¦ط© ط¨ط§ظ„ظ…ط®ط§ط·ط±ط©).
    """
    import math
    bounds = getattr(config, "AI_BOUNDS", {}).get(key)
    if not bounds:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    lo, hi = bounds
    if not (lo <= val <= hi):
        print("self-improve: REJECT {0}={1} (bounds {2}-{3})".format(
            key, raw, lo, hi), flush=True)
        return None
    if key in ("max_loss_usd", "sl_after_entry_usd"):
        ceiling = float(getattr(config, "AI_MAX_STOP_USD", 2.5) or 2.5)
        val = min(val, ceiling)
        cur = float(getattr(config, _PARAM_TARGETS[key], 0.0) or 0.0)
        if cur and val > cur:
            val = min(val, round(cur + 0.10, 2))
    if key == "trailing_back_usd":
        arm = float(getattr(config, "TRAILING_ARM_USD", 1.4) or 1.4)
        if val >= arm:
            val = round(arm * 0.5, 2)
    if key == "trailing_arm_usd":
        if val > float(getattr(config, "PROFIT_TARGET_USD", 1.6) or 1.6):
            val = float(getattr(config, "PROFIT_TARGET_USD", 1.6) or 1.6)
    return round(val, 2)


def _parse_param_block(text):
    """ظٹظ‚ط±ط£ ظƒطھظ„ط© PARAMS ظ…ظ† ط±ط¯ظ‘ ط§ظ„ط¹ظ‚ظ„.

    ظٹظ‚ط¨ظ„ ط§ظ„ط³ط·ط±ظٹظ†:
        PARAMS: momentum_min=1.40, profit_target_usd=2.00
    ط£ظˆ ط§ظ„ط´ظƒظ„ ظ…طھط¹ط¯ظ‘ط¯ ط§ظ„ط£ط³ط·ط± PARAMS: طھط­طھظ‡ key = value ظ„ظƒظ„ ط³ط·ط±.
    ظٹظڈط¹ظٹط¯ dict ظ…ظ† ط§ظ„ط£ط³ظ…ط§ط، ط§ظ„ظ…ط¹ط±ظˆظپط© ظپظ‚ط·.
    """
    import re
    out = {}
    if not text:
        return out
    block = None
    m = re.search(r"PARAMS?\s*:?\s*\n(.*?)(?:\n\s*\n|\Z)", text, re.S | re.I)
    if m:
        block = m.group(1)
    else:
        block = text
    allowed = set(_PARAM_TARGETS) | {"blocked_hours"}
    for k, v in re.findall(r"([a-z_]+)\s*=\s*([0-9][0-9.,\s]*)", block, re.I):
        k = k.lower().strip()
        if k in allowed:
            out[k] = v.strip().rstrip(",")
    return out


def _parse_blocked_hours(raw):
    """يحلّل ساعات الحظر (UTC 0-23) دون تعديل config — للتحقق فقط.

    يرجع قائمة مرتّبة أو None (فارغة/تالفة/ أكثر من 6 ساعات).
    """
    hours = set()
    try:
        for part in str(raw).replace(" ", "").split(","):
            part = part.strip().rstrip(".")
            if part.isdigit():
                h = int(part)
                if 0 <= h <= 23:
                    hours.add(h)
    except Exception:
        return None
    if not hours or len(hours) > 6:
        return None
    return sorted(hours)


def _parse_hour_net(text):
    """يقرأ سطر HOURNET من الخطة: hour=net;n=count لكل ساعة UTC.

   Formato:  HOURNET: 9=+12.30/4, 14=-6.02/7
    يُعيد {hour: net}. يُستخدم للتحقق: لا تُحظر ساعة رابحة أبداً.
    """
    import re
    out = {}
    try:
        m = re.search(r"HOURNET:\s*(.+)", text or "")
        if not m:
            return out
        for part in m.group(1).strip().split(","):
            hm = re.match(r"\s*(\d{1,2})\s*=\s*([+-]?[\d.]+)", part)
            if hm:
                h = int(hm.group(1))
                if 0 <= h <= 23:
                    out[h] = float(hm.group(2))
    except Exception:
        pass
    return out


def _read_hour_net():
    """أرباح/خسائر كل ساعة كما حسبها العقل آخر مرة (دائم عبر الدورات)."""
    try:
        with open(os.path.join("data", "ai_plan.md"), "r",
                  encoding="utf-8") as f:
            return _parse_hour_net(f.read())
    except Exception:
        return {}


def _filter_blocked_hours(proposed, hour_net, min_free=8):
    """يرفض حظر الساعات الرابحة، ويضمن بقاء ساعات تداول كافية.

    القاعدة (طلب صريح: لا تجميد أبداً):
      * ساعة محقّقة ربحاً موجباً لا تُحظر إطلاقاً — حاجز ضد التجميد.
      * بعد كل الحظر (الذي اقترحه + نافذة الجلسة الثابتة) لا يقلّ عدد
        الساعات القابلة للتداول عن min_free، وإلا نرفع أخفّ الحظر.
    يُعيد (ساعات_محظورة, ملاحظات).
    """
    notes = []
    hours = set(proposed)
    # 1) تُحظر ساعة فقط بدليل صافي سالب مُثبت. بلا دليل ⇒ لا حظر إطلاقاً.
    for h in sorted(hours):
        net = hour_net.get(h)
        if net is None:
            hours.discard(h)
            notes.append("hour {0} has no data - NOT blocked".format(h))
        elif net > 0:
            hours.discard(h)
            notes.append("hour {0} profitable ({1:+.2f}) - NOT blocked".format(
                h, net))
    if not hours:
        return set(), notes
    # نافذة الجلسة الثابتة (16-22 افتراضياً) تُحسب كمحظورة ضمنياً
    try:
        sw = float(getattr(config, "SESSION_BLOCK_START_HOUR", 16.0))
        ew = float(getattr(config, "SESSION_BLOCK_END_HOUR", 22.0))
        session = set()
        if getattr(config, "SESSION_BLOCK_ON", False):
            if sw <= ew:
                session = set(range(int(sw), max(int(sw), int(ew))))
            else:
                session = set(range(0, int(ew))) | set(range(int(sw), 24))
    except Exception:
        session = set()

    def free_count(hs):
        return 24 - len(hs | session)
    # 2) إن ضاقت ساعات التداول، نرفع الأخفّolé 먼저 (الأقلّ ضرراً) لا الأسوأ.
    guard = 0
    while free_count(hours) < min_free and hours and guard < 24:
        guard += 1
        mildest = max(hours, key=lambda h: hour_net.get(h, 0.0))
        hours.discard(mildest)
        notes.append("hour {0} unblocked ({1:+.2f}) to keep >= {2} "
                     "tradeable hours".format(
                         mildest, hour_net.get(mildest, 0.0), min_free))
    if free_count(hours) < min_free:
        notes.append("all blocked-hours rejected - keep trading always on")
        return set(), notes
    return hours, notes


def _live_params():
    """المعاملات الحيّة حالياً — تُستخدم كخط أساس وكمحفوظ عند رفض اقتراح."""
    return {
        "momentum_min": round(float(getattr(config, "MOMENTUM_MIN_USD", 1.20)), 2),
        "profit_target_usd": round(
            float(getattr(config, "PROFIT_TARGET_USD", 1.60)), 2),
        "max_loss_usd": round(float(getattr(config, "MAX_LOSS_USD", 2.0)), 2),
        "blocked_hours": sorted(
            getattr(config, "AI_BLOCKED_HOURS", None) or set()),
    }


def _validate_params(candidate):
    """بوابة الاختبار الخلفي — لا مخاطرة على اقتراح غير مُثبت.

    تُرجع (مقبول؟, مقاييس_المرشح, مقاييس_الأساس, سبب).
    basal = المعاملات الحيّة (خط الأساس). أي عجز في العيّنة أو الأفضلية
    ⇒ رفضٌ واحتفاظ بما هو قائم.
    """
    rows = _lab.load_history()
    base = _live_params()
    if len(rows) < 30:
        return (False, {}, {},
                "history too small ({0} trades) - keep live params".format(
                    len(rows)))
    try:
        cand_m = _lab.backtest(candidate, rows)
        base_m = _lab.backtest(base, rows)
    except Exception as exc:
        return False, {}, {}, "backtest error: {0!r}".format(exc)
    ok, why = _lab.compare(cand_m, base_m)
    if ok:
        _lab.knowledge_append(
            "ACCEPTED {0} -> {1}".format(
                ",".join("{0}={1}".format(k, v)
                         for k, v in sorted(candidate.items())), why))
    return ok, cand_m, base_m, why


def _apply_blocked_hours(raw, hour_net=None, min_free=8):
    """يطبّق ساعات الحظر بعد التحقق منها (لا تجميد، لا حظر لساعة رابحة)."""
    hours = _parse_blocked_hours(raw)
    if hours is None:
        return None
    hours, notes = _filter_blocked_hours(
        hours, hour_net if hour_net is not None else _read_hour_net(),
        min_free)
    for n in notes:
        print("blocked_hours guard: " + n, flush=True)
    config.AI_BLOCKED_HOURS = set(hours)
    return sorted(hours)


def _read_recommended_params():
    """طھظˆطµظٹط§طھ ط§ظ„ط¹ظ‚ظ„ ظ…ظ† ط§ظ„ظ…ظ„ظپ ط§ظ„ط¯ط§ط¦ظ… data/ai_plan.md.

    md ط؛ظٹط± ظ…ط¹ط²ظˆظ„ â‡’ ظٹطµظ„ ط§ظ„ط¯ظˆط±ط© ط§ظ„طھط§ظ„ظٹط© ط¹ط¨ط± persist.-shape ط§ظ„ظ‚ط¯ظٹظ…
    APPLIED_SETTING/MOMENTUM_MIN_x ظ…ط¯ط¹ظˆظ… ظƒط§ط­طھظٹط§ط·طŒ ظˆai_recommendations.json
    ظƒط¢ط®ط± ط§ط­طھظٹط§ط·.
    """
    import re
    try:
        with open(os.path.join("data", "ai_plan.md"), "r",
                  encoding="utf-8") as f:
            txt = f.read()
        blk = _parse_param_block(txt)
        if blk:
            return blk
        m = re.search(r"MOMENTUM_MIN\s*=\s*(-?\d+\.?\d*)", txt)
        if m:
            return {"momentum_min": m.group(1)}
    except Exception:
        pass
    rec = _read_json(os.path.join("data", "ai_recommendations.json"))
    val = rec.get("momentum_min")
    if val is not None:
        return {"momentum_min": val}
    return {}


def _journal(state, applied, skipped):
    """ظٹط³ط¬ظ‘ظ„ ظ‡ط°ظ‡ ط§ظ„ط¶ط¨ط·ط© + ط­طµظٹظ„ط© ظ…ط§ طھظ„ط§ظ‡ط§ (طھط؛ط°ظٹط© ظ…ط؛ظ„ظ‚ط© ظ„ظ„ط¯ظˆط±ط© ط§ظ„طھط§ظ„ظٹط©)."""
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
        parts = ["\n## {0} UTC".format(stamp)]
        if applied:
            parts.append("- APPLIED: " + ", ".join(
                "{0}={1}".format(k, v) for k, v in sorted(applied.items())))
        if skipped:
            parts.append("- SKIPPED: " + ", ".join(
                "{0}={1}".format(k, v) for k, v in sorted(skipped.items())))
        parts.append("- realized_now: {0}".format(
            state.get("last_balance") or "?"))
        with open(AI_JOURNAL, "a", encoding="utf-8") as f:
            f.write("\n".join(parts) + "\n")
        with open(AI_JOURNAL, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 200:
            with open(AI_JOURNAL, "w", encoding="utf-8") as f:
                f.writelines(lines[-180:])
    except Exception as exc:
        print("journal warn: {0!r}".format(exc), flush=True)


def apply_self_improvement(state):
    """طھط·ط¨ظٹظ‚ طھظˆطµظٹط§طھ ط§ظ„ط¹ظ‚ظ„ ط¹ظ„ظ‰ config ظپظٹ ط§ظ„ط°ط§ظƒط±ط©طŒ طھط­طھ config.AI_BOUNDS.

    ظٹظ‚ط±ط£ ظƒطھظ„ط© PARAMS ظ…ظ† data/ai_plan.md ط§ظ„ط¯ط§ط¦ظ…. ظƒظ„ ظ‚ظٹظ…ط© ط¯ط§ط®ظ„ ط­ط¯ظ‘ظ‡ط§ طھظڈط·ط¨ظژظ‘ظ‚طŒ
    ظˆط§ظ„ظ…ط¹ط·ظˆط¨ط© طھظڈطھط¬ط§ظ‡ظ„è¯¥é،¹ ظپظ‚ط·. ط§ظ„ظ„ظˆطھ ظ„ط§ ظٹظڈظ…ظژط³طŒ ظˆظ„ط§ ظ…ظ„ظپ config ظٹظڈظƒطھط¨طŒ ظˆظ„ط§
    commit â€” ط§ظ„طھط¹ط¯ظٹظ„ ط³ط±ظ‘ظٹ ظپظٹ ط§ظ„ط°ط§ظƒط±ط© ظپظٹط³ط±ظٹ ظپظˆط±ط§ظ‹. ظٹظڈط³طھط¯ط¹ظ‰ ظƒظ„ ط¯ظˆط±ط©طŒ ظˆط§ظ„ط¹ظ‚ظ„
    ظٹط¹ظٹط¯ ط§ظ„طھظ‚ظٹظٹظ… ظƒظ„ ط³ط§ط¹ط© (AI_INTERVAL_MIN=60).
    """
    if not (AI_ON and AI_APPLY_ON):
        return {"applied": False, "reason": "self-tune disabled"}
    try:
        rec = _read_recommended_params()
        hour_net = _read_hour_net()
        if not rec:
            return {"applied": False, "reason": "no recommendation"}
        applied, skipped = {}, {}
        for key, target in _PARAM_TARGETS.items():
            if key not in rec:
                continue
            safe = _clamp_param(key, rec[key])
            if safe is None:
                skipped[key] = rec[key]
                continue
            setattr(config, target, safe)
            applied[key] = safe
        if "blocked_hours" in rec:
            bh = _apply_blocked_hours(rec["blocked_hours"], hour_net)
            if bh is not None:
                applied["blocked_hours"] = bh
            else:
                skipped["blocked_hours"] = rec["blocked_hours"]
        else:
            # العقل لم يذكر حظراً ⇒ يطلق كل ما حظره سابقاً (لا تجميد دائم)
            if getattr(config, "AI_BLOCKED_HOURS", None):
                config.AI_BLOCKED_HOURS = set()
                applied["blocked_hours"] = []
                print("blocked_hours released - brain proposed none", flush=True)
        state["yh_dyn"] = dict(applied)
        state["ai_applied"] = applied
        if applied:
            _journal(state, applied, skipped)
            print("self-improve APPLIED: " + ", ".join(
                "{0}={1}".format(k, v) for k, v in sorted(applied.items())),
                flush=True)
        return {"applied": bool(applied), "applied_params": applied,
                "skipped": skipped}
    except Exception as exc:
        print("self-improve fail: {0!r}".format(exc), flush=True)
        return {"applied": False, "reason": repr(exc)}

