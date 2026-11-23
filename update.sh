#!/bin/bash
set -e
echo "============================================="
echo "   Skyrex Computers - Server Updater"
echo "============================================="
cd /var/www/skyrex

echo "[1/4] Pulling latest code from Git..."
git fetch origin main
git reset --hard origin/main

echo "[2/4] Updating Python dependencies..."
/var/www/skyrex/venv/bin/pip install -r /var/www/skyrex/requirements.txt -q

echo "[3/4] Ensuring file permissions & systemd units..."
chmod +x /var/www/skyrex/update.sh 2>/dev/null || true
chmod +x /var/www/skyrex/run_tg_bot.py 2>/dev/null || true

# Auto-sync systemd units if modified
if [ -f /var/www/skyrex/skyrex.service ]; then
    cp /var/www/skyrex/skyrex.service /etc/systemd/system/skyrex.service
    systemctl daemon-reload
fi
if [ -f /var/www/skyrex/skyrex-tg-bot.service ]; then
    cp /var/www/skyrex/skyrex-tg-bot.service /etc/systemd/system/skyrex-tg-bot.service
    systemctl daemon-reload
    systemctl enable skyrex-tg-bot 2>/dev/null || true
fi

echo "[4/4] Restarting skyrex systemd service..."
systemctl restart skyrex
systemctl restart skyrex-tg-bot 2>/dev/null || true

echo ""
echo "[✓] Skyrex successfully updated and restarted!"
systemctl status skyrex --no-pager -n 5
