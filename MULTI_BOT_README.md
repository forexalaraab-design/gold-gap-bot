# بوت التحليل اليومي متعدد الأزواج

## 📋 الوصف
بوت يفحص **كل الأزواج** يومياً ساعة 08:00 UTC، يحلل:
- **البيانات الاقتصادية** من التقويم
- **الأخبار والمشاعر** من RSS
- **اتجاهات كبار المتداولين** من COT report
- **التحليل الفني** من Yahoo Finance
- **آراء المحللين** من Yahoo consensus

إذا وجد فرصة مناسبة (`score >= 70%`) ينفذها تلقائياً مع:
- **وقف الخسارة** ديناميكي بناءً على ATR
- **هدف الربح** بنسبة ربح/خسارة 1.5x
- **حجم صفقة** بناءً على الرصيد والمخاطرة 1%

---

## 📁 الملفات

```
C:/Users/1234/Desktop/مجلد جديد (2)/multi_bot/
├── __init__.py
├── config.py          # إعدادات متعددة الأزواج
├── calendar.py        # تقويم اقتصادي + فلتر أحداث
├── sentiment.py       # تحليل مشاعر من RSS
├── analyst.py         # آراء المحللين + COT + Yahoo
├── scanner.py         # فحص كل الأزواج وتقييم الفرص
├── risk.py            # حساب SL/TP ديناميكي + حجم الصفقة
├── executor.py        # تنفيذ الصفقات عبر MT5
└── scheduler.py       # جدولة يومية + حدود يومية

C:/Users/1234/Desktop/مجلد جديد (2)/
├── main_multi.py      # نقطة البداية
├── requirements_multi.txt
└── .github/workflows/multi-bot.yml
```

---

## ⚙️ الإعدادات السريعة

### 1. تثبيت MT5
- ثبّت **MetaTrader 5** على Windows
- سجّل دخول بحساب FP Markets / Fusion Markets Demo
- انسخ المسار: `C:\Program Files\MetaTrader 5\terminal64.exe`

### 2. متغيرات البيئة
```bash
# Linux/Mac
export MT5_LOGIN=490512
export MT5_PASSWORD="***"
export MT5_SERVER="FPMarkets-Demo"
export MT5_PATH="C:\Program Files\MetaTrader 5\terminal64.exe"
export MULTI_SCAN_HOUR=8
export MULTI_MIN_CONFIDENCE=0.70
export MULTI_MAX_TRADES=3
```

### 3. تشغيل محلي
```bash
pip install -r requirements_multi.txt
python main_multi.py
```

### 4. تشغيل على GitHub Actions
أضف الأسرار:
- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`
- `MT5_PATH`

---

## 📊 الأزواج المدعومة
```
EURUSD, GBPUSD, USDJPY, USDCHF
AUDUSD, NZDUSD, USDCAD, XAUUSD
```

---

## 🎯 آلية العمل

### كل يوم 08:00 UTC:
1. **جلب التقويم الاقتصادي** من Forex Factory
2. **فحص كل زوج:**
   - تحليل فني (35%)
   - أحداث اقتصادية (25%)
   - مشاعر السوق (20%)
   - آراء المحللين (15%)
   - اتجاهات كبار المتداولين (5%)
3. **إذا كان `score >= 70%`:**
   - حساب SL/TP ديناميكي
   - حساب حجم الصفقة بناءً على الرصيد
   - تنفيذ الصفقة عبر MT5
4. **مراقبة + إغلاق تلقائي**

---

## ⚠️ ملاحظات مهمة

1. **لا يفتح صفقات قبل/بعد أحداث مهمة** (NFP, CPI, FOMC) بـ 30 دقيقة
2. **حجم الصفقة** دائماً 0.01 لوت كحد أدنى (1$ لكل نقطة)
3. **حدود يومية:** أقصى 3 صفقات يومياً + 3% خسارة كحد أقصى
4. **MT5 مطلوب:** البوت يعمل فقط عبر MT5 لأنه يقبل SL/TP
5. **لا يوجد تنبيه:** البوت ينفذ تلقائياً، راقب `data/multi_trades.csv`

---

## 🔧 تعديل الإعدادات

### تعديل ساعة الفحص:
```bash
# فحص كل ساعتين بدلاً من يومياً
MULTI_SCAN_HOUR=8
MULTI_SCAN_MINUTE=0
# في GitHub Actions: cron '0 8,10,12,14,16,18,20 * * *'
```

### تعديل حد الثقة:
```bash
MULTI_MIN_CONFIDENCE=0.75  # فقط فرص >75%
```

### تعديل المخاطرة:
```bash
MULTI_RISK_PCT=0.02        # 2% من الرصيد لكل صفقة
MULTI_MAX_DAILY_LOSS=0.05  # 5% خسارة يومية كحد
```

---

## 📈 تتبع النتائج

```bash
# سجل الصفقات
data/multi_trades.csv

# الفرص اليومية
data/opportunities.json

# حالة البوت
data/multi_bot_state.json
```

---

## 🐛 استكشاف الأخطاء

### MT5 لا يفتح:
- تأكد من تثبيت MT5
- تأكد من صحة `MT5_PATH`
- تأكد من بيانات الدخول

### لا توجد فرص:
- طبيعي: البوت ينتظر فرصة `score >= 70%`
- يمكن خفض `MULTI_MIN_CONFIDENCE` إلى 0.60

### أخطاء في التقويم:
- Forex Factory API قد يكون محظور
- استخدم VPN أو بديل

---

**تم البناء:** 2026-10-XX
**الحالة:** جاهز للتشغيل بعد تثبيت MT5
