#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] AfterBlockTraffic: instance deregistered from ALB, stopping app" >> $LOG

# Instance has zero live traffic — safe to stop the app.
if systemctl is-active --quiet my-app 2>/dev/null; then
    systemctl stop my-app
    echo "[$TIMESTAMP] AfterBlockTraffic: stopped via systemd" >> $LOG
else
    # Fall back for processes not yet managed by systemd (first deploy)
    pkill -f "python3 /var/www/my-app/main.py" || true
    echo "[$TIMESTAMP] AfterBlockTraffic: stopped via pkill" >> $LOG
fi

# Remove the draining flag so the new version starts clean
rm -f /var/www/my-app/draining

# Flush pending writes to disk before deployment overwrites files
sync

echo "[$TIMESTAMP] AfterBlockTraffic: done" >> $LOG
