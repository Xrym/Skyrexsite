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

echo "[3/4] Ensuring file permissions..."
chmod +x /var/www/skyrex/update.sh 2>/dev/null || true

echo "[4/4] Restarting skyrex systemd service..."
systemctl restart skyrex

echo ""
echo "[✓] Skyrex successfully updated and restarted!"
systemctl status skyrex --no-pager -n 5
