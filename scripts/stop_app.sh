#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] ApplicationStop: stopping my-app before new revision is installed" >> $LOG

# Stop via systemd if the unit exists and is active
if systemctl is-active --quiet my-app 2>/dev/null; then
    systemctl stop my-app
    # Wait up to 10s for the process to fully exit
    WAITED=0
    while systemctl is-active --quiet my-app 2>/dev/null && [ $WAITED -lt 10 ]; do
        sleep 1
        WAITED=$((WAITED + 1))
    done
    echo "[$TIMESTAMP] ApplicationStop: stopped via systemd after ${WAITED}s" >> $LOG

elif pgrep -f "python3 /var/www/my-app/main.py" > /dev/null 2>&1; then
    # First deployment — systemd unit does not exist yet, process was
    # started manually or by a previous nohup. Kill it gracefully (SIGTERM),
    # then SIGKILL if it does not exit within 5s.
    pkill -TERM -f "python3 /var/www/my-app/main.py" || true
    WAITED=0
    while pgrep -f "python3 /var/www/my-app/main.py" > /dev/null 2>&1 && [ $WAITED -lt 5 ]; do
        sleep 1
        WAITED=$((WAITED + 1))
    done
    pkill -KILL -f "python3 /var/www/my-app/main.py" || true
    echo "[$TIMESTAMP] ApplicationStop: stopped via pkill after ${WAITED}s" >> $LOG

else
    echo "[$TIMESTAMP] ApplicationStop: app was not running, nothing to stop" >> $LOG
fi

# Confirm port 8080 is free before handing off to BeforeInstall
if ss -tlnp | grep -q ':8080'; then
    echo "[$TIMESTAMP] ApplicationStop: WARNING — port 8080 still in use after stop" >> $LOG
else
    echo "[$TIMESTAMP] ApplicationStop: port 8080 is free" >> $LOG
fi
