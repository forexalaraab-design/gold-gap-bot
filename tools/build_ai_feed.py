# -*- coding: utf-8 -*-
"""build_ai_feed.py — يولّد data/ai_feed.md من data/trades.csv (مجرّد).

الأداة تُحوّل سجل الصفقات الخام إلى سطور محايدة يقرأها ai_brain داخل
الدورة الحية (الـ runner لا يصله trades.csv لأنه معزول بـ gitignore،
انظر القاعدة 0 في AGENTS.md — لا تُرفع سجلات تكشف المنطق).

صيغة السطر (يطابق main._record_close):
    ts_close | side | pnl_net | W/L/SL/TP | spread

- side يُختصر B/S (محايد، لا يكشف منطق).
- reason يُختزل: sl→SL، tp→TP، وإلا W حسب إشارة الربح.
- بلا أسماء(fields) ولا أسباب داخلية (giveback/no_progress…).

الاستخدام:  python tools/build_ai_feed.py [--limit N]
"""

import argparse
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TRADES = os.path.join(ROOT, "data", "trades.csv")
OUT = os.path.join(ROOT, "data", "ai_feed.md")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _side(s):
    s = str(s or "").strip().lower()
    if s in ("buy", "b", "1", "0"):
        return "B"
    if s in ("sell", "s", "2"):
        return "S"
    return "B" if s not in ("", "none") else "?"


def rows_from_csv(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = [r for r in csv.reader(f)][1:]
    out = []
    for r in raw:
        # السجل混有两个 schema: قديم 10 أعمدة وجديد 12 عموداً
        if len(r) >= 12:
            ts, side, pnl, reason, spread = r[1], r[2], r[10], r[11], r[9]
        elif len(r) == 10:
            ts, side, pnl, reason, spread = r[1], r[2], r[8], r[9], ""
        else:
            continue
        p = _num(pnl)
        if p is None:
            continue
        tag = {"sl": "SL", "max_loss": "SL", "tp": "TP",
               "profit_target": "TP"}.get(str(reason or "").lower(),
                                          "W" if p > 0 else "L")
        ts_fmt = str(ts or "")[:16].replace("T", " ")
        sp = _num(spread)
        out.append((ts_fmt, _side(side), round(p, 2), tag,
                    round(sp, 2) if sp is not None else ""))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="اكتفِ بآخر N صفقة (0 = الكل)")
    args = ap.parse_args()
    if not os.path.exists(TRADES):
        raise SystemExit("missing data/trades.csv")
    rows = rows_from_csv(TRADES)
    if args.limit and len(rows) > args.limit:
        rows = rows[-args.limit:]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for ts, side, pnl, tag, sp in rows:
            f.write("{0}|{1}|{2}|{3}|{4}\n".format(ts, side, pnl, tag, sp))
    wins = len([r for r in rows if r[2] > 0])
    print("wrote {0} rows -> {1}".format(len(rows), OUT))
    print("net={0:.2f} win%={1:.0f}".format(
        sum(r[2] for r in rows),
        100.0 * wins / max(1, len(rows))))


if __name__ == "__main__":
    main()
