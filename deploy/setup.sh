#!/usr/bin/env bash
# ============================================================
# تثبيت البوت على Oracle Cloud Always Free (Ubuntu 24.04)
# التشغيل:  sudo bash deploy/setup.sh
# الشرط: المستودع منسوخ إلى /opt/gold-gap-bot وملف .env موجود
#         فيه (انظر deploy/.env.example). لا يفتح البوت صفقات ما لم
#         يُضبط STRAT_PAUSE_OPEN=0 في .env.
# ============================================================
set -euo pipefail

DIR="/opt/gold-gap-bot"
if [ ! -f "$DIR/live.py" ]; then
  echo "ERROR: $DIR/live.py غير موجود. انسخ المستودع أولاً."
  exit 1
fi
if [ ! -f "$DIR/.env" ]; then
  echo "ERROR: $DIR/.env غير موجود. انسخه من deploy/.env.example ثم املأ الأسرار."
  exit 1
fi

cd "$DIR"

# 1) البيئة الافتراضية والاعتمادات
if [ ! -d "$DIR/.venv" ]; then
  echo "[1/5] installing python3-venv + deps ..."
  apt-get update -y
  apt-get install -y python3.12-venv python3.12-dev git curl
  python3 -m venv "$DIR/.venv"
fi
echo "[2/5] pip install ..."
"$DIR/.venv/bin/pip" install --upgrade pip
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

# 2) مستخدم نظام مخصص (ليس root)
echo "[3/5] creating service user 'goldgap' ..."
if ! id -u goldgap >/dev/null 2>&1; then
  useradd --system --home "$DIR" --shell /usr/sbin/nologin goldgap
fi
chown -R goldgap:goldgap "$DIR"

# 3) وحدة systemd
echo "[4/5] installing systemd unit ..."
cp "$DIR/deploy/goldgap.service" /etc/systemd/system/goldgap.service
systemctl daemon-reload
systemctl enable goldgap.service
systemctl restart goldgap.service

# 4) فحص
echo "[5/5] status:"
sleep 3
systemctl --no-pager --lines=15 status goldgap.service || true
echo
echo "============================================================"
echo "done. متابعة السجلات:"
echo "  sudo journalctl -u goldgap -f"
echo "إعادة التشغيل:        sudo systemctl restart goldgap"
echo "إيقاف الفتح مؤقتاً:   عدّل STRAT_PAUSE_OPEN=1 في $DIR/.env"
echo "                        ثم: sudo systemctl restart goldgap"
echo "============================================================"