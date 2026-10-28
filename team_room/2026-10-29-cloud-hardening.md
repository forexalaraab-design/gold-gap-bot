# cloud-hardening — 2026-10-29

**البند المطروح:** بعد أول تشغيل سحابي أخضر (`40784422191`)، ما الثغرات الباقية
التي قد تُبطل الاختبار الهندسي 4 أسابيع؟

**الحالة قبل الجلسة:**
- الرصيد: $91.56 · صفقات مفتوحة: 0 · التنفيذ: `execution_disabled`
- الـ workflow: `active` · cron `0 6,12,18 * * *`
- آخر تشغيل سحابي: **نجح** — `[mt5] connected attempt=1 equity=91.56`، 9/9 رموز

---

## 1) الاستدعاء
**الخبير:** مهندس موثوقية (reliability / fail-loud) — لأن الخطر الباقي ليس في
الإشارة بل في **صمت الأعطال**: تشغيل يبدو أخضر وهو لم يقرأ سعراً.

## 2) v1 — المهندس
1. كفى؛ التشغيل أخضر والأسباب تُكتب، فلا حاجة لتعديل.
2. نرفع مدة الاحتفاظ بالسجلات.

## 3) التدمير
**محامي الشيطان:**
- **عيب قاتل #1:** إن فشل MT5 في السحابة، `main_multi.py` يطبع سطراً ودياً
  ويكمل — فيظهر التشغيل **أخضر** وهو لم يقرأ ولا رمزاً. عطل صامت في أداة
  هدفها الوحيد إثبات أن MT5 يعمل. يجب أن يكون الخروج **فاشلاً** (`exit 2` +
  `::error::`).
- **عيب قاتل #2:** الحد اليومي (`MULTI_MAX_TRADES=1`) كان يُقرأ من
  `data/multi_state.json`، و`data/*.json` **مستثنى من git** ⇒ ملف الحالة يعود
  فارغاً كل دورة ⇒ الحد عديم الأثر. الحقيقة الوحيدة الموثوقة هي **سجل ديلات
  الوسيط**.
- **عيب قاتل #3:** سجلات الاختبار (سبب كل رفض) تُكتب في `data/` ثم **تُمحى**
  مع الـ runner. اختبار 4 أسابيع بلا أرشيف = صفر دليل.

**الزبون الغبي:** تقولون "الاختبار يثبت أن MT5 يعمل". وأنا أرى تشغيماً أخضر
لم يُثبت شيئاً، وحدّاً يومياً لا يعدّ شيئاً، وسجلاً يُمحى كل 20 دقيقة. ماذا
يبقى من الأربعة أسابيع؟

## 4) التصادم والتصحيح
**الخبير:** شرط القبول ليس "نجح التشغيل"، بل **"لا يمكن أن ينجح كذباً"**:
فشل MT5 = فشل التشغيل، والعدّ من الوسيط، والدليل في artifact.
**المهندس (v2):**
- `guard.trades_opened_today()` — يعدّ ديلات الدخول من `history_deals_get`.
- `can_trade_today()` = `max(محلي, وسيط)` — الوسيط هو الحاكم.
- `main_multi.py` يخرج بـ **2** عند فشل MT5، ويطبع `opened_today` للتشخيص.
- `actions/upload-artifact@v4` (14 يوماً) بدل خطوة self-dispatch الفارغة.

## 5) قرار المايسترو

| البند | القرار |
|---|---|
| فشل MT5 في السحابة | **فشل تشغيل صريح** (`exit 2` + `::error::`) — لا نجاح كاذب |
| الحد اليومي | **من الوسيط** (`history_deals_get`)، `max(محلي, وسيط)` |
| دليل الاختبار | **artifact** 14 يوماً: `scan_reasons`, `opportunities`, `multi_trades`, `multi_state` |
| self-dispatch | **محذوف** — كان خطوة فارغة تُطيل كل تشغيل |
| المال | **صفر** — `MULTI_EXECUTE=0` + بوابة 300$ |
| المدة | 4 أسابيع، ثم جلسة جديدة |

---

## 6) بند طارئ اكتُشف أثناء التحقق — القراءة الفارغة الكاذبة

**الدليل من السحابة (تشغيل `40784907519`):**
```
23:07:23  [multi] MT5 connected | equity=91.56 positions=0 opened_today=0
23:07:35  [multi] safety: blocked kill_daily {'day_pnl': -111.8, ...}
```
نفس الدالة، نفس النافذة — **صفر** ثم **−111.8** بعد 12 ثانية. أي أن
`history_deals_get` ترجع **فارغة كذباً** في الثواني الأولى بعد إقلاع
التيرمنال. وهذا بالحرف **نفس صنف العطل** الذي فتح 129 صفقة: قراءة فارغة
تُفسَّر "لا تعرّض" ⇒ سماح.

**الإصلاح (fail-closed):**
- `guard.warmup_history(days=30, timeout=45s)` — ينتظر ظهور ديلات؛ ثم
  يسجّل التفصيل. بعد المهلة: حكم "حساب فارغ حقاً" لا "غير معروف".
- `guard.history_synced()` + `account_exposure()` تُعيد
  `guard_history_unsynced` إذا لم يُزامَن السجل.
- `execution_gate()` يرفض التنفيذ عند سجل غير مُزامَن.

**التحقق في السحابة (تشغيل `40785375438`):**
```
[multi] history warmup: synced=True deals_30d=4175 after 3s
[multi] broker truth | opened_today=179 deals_today={'deals': 358, 'entries': 179, 'exits': 179} equity=91.56 positions=0
[multi] scan done: 1 opportunities | rejects: {'passed': 3, 'below_threshold': 6}
[multi] execution blocked: execution_disabled
[multi] safety: blocked kill_daily {'day_pnl': -111.8, 'month_pnl': -266.93}
```
الرقم انتقل من **0** إلى **179** — أي أن عطل القراءة الفارغة أُغلق بدليل،
لا بادّعاء.

---

## 7) التحقق المحلي

```
[mt5] connected attempt=1 path=default login=490512 server=FusionMarkets-Demo equity=91.56
[multi] MT5 connected | equity=91.56 positions=0 opened_today=179
[multi] scan done: 1 opportunities | rejects: {'below_threshold': 8, 'passed': 1}
[multi]   NZDUSD SELL score=-0.33 entry=0.56265 sl=0.53666 tp=0.5852 lots=0.01 src=mt5
[multi] execution blocked: execution_disabled
[multi] safety: blocked kill_daily {'day_pnl': -111.8, 'month_pnl': -266.93}
[multi] finished: scanned=1, executed=0
```

- `opened_today=179` = **حقيقة الوسيط** (عدد صفقات 2026-10-28). هذا الرقم من
  سجل الديلات مباشرة، وهو الذي كان صفراً في ملف الحالة.
- `py_compile` نظيف على 6 ملفات.
- بوابتان عملتا: `execution_disabled` ثم `kill_daily`.

## ما تغيّر فعلياً
- [x] `multi_bot/guard.py` — `trades_opened_today()` · `day_deal_stats()` · `warmup_history()` · `history_synced()`
- [x] `multi_bot/scheduler.py` — `max(local, broker)` + `guard_history_unsynced`
- [x] `main_multi.py` — `exit 2` عند فشل MT5 + تسخين السجل + سطر "broker truth"
- [x] `.github/workflows/multi-bot.yml` — artifact (14 يوماً) بدل self-dispatch
- [ ] **مال/تنفيذ: لا شيء**
