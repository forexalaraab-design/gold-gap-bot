تثبيت البوت على Oracle Cloud Always Free
=========================================

1) إنشاء الحساب والـ VM (مرة واحدة، يحتاج بطاقة لتوثيق فقط — لا شحن):
   - سجل في cloud.oracle.com → Core → Compute → Create Instance
   - الشكل (Shape): VM.Standard.A1.Flex (ARM) 4 OCPU / 24 GB (مجاني دائماً)
   - صورة النظام: Ubuntu 24.04 (aarch64)
   - مفتاح SSH: أنشئه من البوابة ثم نزّله لجهازك
   - قواعد الأمان (Security List): لا تفتح أي منفذ — الاتصال صادر فقط
     (البوت يحتاج outbound HTTPS فقط: cTrader + Yahoo + gold-api)

2) نقل المستودع والنموذج:
     scp -i key.pem -r . ubuntu@<VM_IP>:/tmp/repo
   ثم على الـ VM:
     sudo mkdir -p /opt/gold-gap-bot
     sudo rsync -a /tmp/repo/ /opt/gold-gap-bot/
     cp /opt/gold-gap-bot/deploy/.env.example /opt/gold-gap-bot/.env
     nano /opt/gold-gap-bot/.env        # أضف الأسرار الحقيقية
     chmod 600 /opt/gold-gap-bot/.env

3) التثبيت (يشغّل البوت كخدمة systemd مع إعادة تلقائية عند أي تعليق):
     cd /opt/gold-gap-bot
     sudo bash deploy/setup.sh

4) المتابعة اليومية:
     sudo journalctl -u goldgap -f      # سجل حي
     sudo systemctl restart goldgap      # إعادة تشغيل
     sudo systemctl stop goldgap         # إيقاف البوت كاملاً
   بيانات/سجلات الصفقات: /opt/gold-gap-bot/data/
   (بما فيها data/v2_virtual.csv — تقييم v2 الافتراضي).

5) إيقاف/استئناف الفتح من .env:
     STRAT_PAUSE_OPEN=1   → راقب فقط (لا صفقات جديدة)
     STRAT_PAUSE_OPEN=0   → استئناف التداول الحي
   ثم: sudo systemctl restart goldgap
   (على GitHub Actions نفسها نفس المتغير كـ Actions variable).

ملاحظات:
- تطبيق OpenAPI: غيّر اسمه في بوابة id.ctraderapi.com إلى اسم محايد
  (TradeDesk/Alpha Desk…) قبل الترحيل — الاسم الحالي يظهر كـ
  openapi_GoldGapBot على كل صفقة من جهة المنصة (بند AGENTS §0.5).
- رموز cTrader Access Token تنتهي بعد مدة طويلة؛ حدّثها في .env عند
  طلب الوسيط للتجديد (سيظهر أخطاء 401 في السجل).