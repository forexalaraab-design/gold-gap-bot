# 🔵 Multi-Pair Daily Bot — Cloud Deployment Guide

## ✅ الهدف
تشغيل البوت على **سحابة GitHub** بدون حاسوبك الشخصي.

## 🏗️ المتطلبات
1. **VPS** (Windows Server أو Ubuntu) أو **سيرفر خاص**
2. **MetaTrader 5** مثبت على السيرفر
3. **حساب MT5 Demo/Real** على FP Markets أو Fusion Markets
4. **GitHub repository** لهذا المشروع
5. **GitHub Self-Hosted Runner** مسجل على السيرفر

---

## 📋 الخطوات

### 1) إعداد السيرفر
- أوقف السيرفر
- ثبّت Windows Server 2022 أو Ubuntu 22.04
- ثبّت **MetaTrader 5** على السيرفر
- سجّل دخول MT5 بحساب Demo/Real
- تأكد من فتح منفذ 443/80 للاتصال بـ GitHub Actions

### 2) إعداد GitHub Self-Hosted Runner
1. اذهب إلى **GitHub Repository → Settings → Actions → Runners → New self-hosted runner**
2. اختر **Windows** أو **Linux** حسب السيرفر
3. اتبع التعليمات لتنزيل وتشغيل Runner على السيرفر
4. اسم الـ runner: `multi-bot-server`
5. تأكد من ظهوره في قائمة Runners بحالة **Online**

### 3) إعداد MT5 على السيرفر
- MT5 يجب أن يعمل **دائماً** (كخدمة Windows أو systemd)
- أو يمكن تشغيله يدوياً قبل كل run
- البوت سيتصل بـ MT5 المحلي على السيرفر

### 4) إعداد GitHub Secrets
أضف هذه الأسرار في **GitHub → Settings → Secrets and variables → Actions**:

| الاسم | القيمة |
|-------|--------|
| `MT5_LOGIN` | رقم حساب MT5 |
| `MT5_PASSWORD` | كلمة سر MT5 |
| `MT5_SERVER` | اسم السيرفر (مثل `FPMarkets-Demo`) |
| `MT5_PATH` | `C:\Program Files\MetaTrader 5\terminal64.exe` (Windows) |
| `MULTI_SCAN_HOUR` | `8` |
| `MULTI_SCAN_MINUTE` | `0` |
| `MULTI_MIN_CONFIDENCE` | `0.70` |
| `MULTI_MAX_TRADES` | `3` |
| `MULTI_RISK_PCT` | `0.01` |

### 5) جدولة العمل
البوت يعمل تلقائياً كل يوم **08:00 UTC**.

لتشغيله يدوياً:
- GitHub → Actions → Multi-Pair Daily Bot → Run workflow

---

## 🔧 بنية المشروع على GitHub

```
Repository (github.com/your-repo/gold-gap-bot)
  ├── .github/workflows/multi-bot.yml   # ← يعمل على self-hosted runner
  ├── main_multi.py                     # ← نقطة البداية
  ├── multi_bot/
  │   ├── config.py
  │   ├── calendar.py
  │   ├── sentiment.py
  │   ├── analyst.py
  │   ├── scanner.py
  │   ├── risk.py
  │   ├── executor.py
  │   └── scheduler.py
  ├── requirements_multi.txt
  └── data/                             # ← يُرفع تلقائياً بعد كل run
```

---

## 🚀 كيف يعمل

```
GitHub Actions (cron يومياً 08:00 UTC)
  ↓
Self-Hosted Runner (على سيرفرك)
  ↓
  ├── pip install requirements
  ├── python main_multi.py
  │     ├── فحص 8 أزواج
  │     ├── تحليل + تقييم الفرص
  │     └── تنفيذ الصفقات عبر MT5 المحلي
  └── رفع logs/opportunities إلى GitHub Artifacts
```

---

## ⚠️ ملاحظات مهمة

### 1. MT5 يجب أن يعمل دائماً
على Windows Server، اجعل MT5 يبدأ تلقائياً عند الإقلاع:
```powershell
# Schedule task or startup script
Start-Process "C:\Program Files\MetaTrader 5\terminal64.exe"
```

### 2. السيرفر يجب أن يكون متصلاً بالإنترنت
- البوت يجلب بيانات من Yahoo Finance + Forex Factory
- إذا انقطع الإنترنت، البوت يتوقف حتى يعود الاتصال

### 3. الأمان
- لا تشارك بيانات MT5 مع أحد
- استخدم حساب Demo للتجربة
- اضبط `MAX_DAILY_LOSS` لحماية الرصيد

### 4. التكاليف
- GitHub Actions: مجاني لـ 2000 دقيقة/شهر
- Self-Hosted Runner: مجاني على GitHub
- VPS: ~$5-10/شهر (DigitalOcean, AWS Lightsail, etc.)

---

## 📊 المراقبة

### GitHub Actions Logs
- Repository → Actions → Multi-Pair Daily Bot → View logs

### بيانات البوت
```bash
# بعد كل run، البيانات تُرفع تلقائياً إلى:
data/multi_trades.csv        # سجل الصفقات
data/opportunities.json      # الفرص اليومية
data/multi_bot_state.json    # حالة البوت
```

---

## 🐛 استكشاف الأخطاء

### Runner غير متصل
- تحقق من اتصال السيرفر بالإنترنت
- تحقق من تشغيل خدمة Runner
- أعد تشغيل Runner

### MT5 لا يفتح
- تأكد من تثبيت MT5 على السيرفر
- تأكد من صحة `MT5_PATH`
- تأكد من بيانات الدخول

### لا توجد فرص
- طبيعي: البوت ينتظر فرصة `score >= 70%`
- يمكن خفض `MULTI_MIN_CONFIDENCE` إلى 0.60

---

## 📞 الدعم

إذا واجهت مشاكل:
1. تحقق من GitHub Actions logs
2. تحقق من `data/multi_trades.csv`
3. تواصل معي

---

**تم الإنشاء:** 2026-10-XX
**الحالة:** جاهز للنشر على السحابة
