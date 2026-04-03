#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] ApplicationStart: starting my-app" >> $LOG

systemctl start my-app

# Wait up to 30s for the app to bind to port 8080
WAITED=0
while [ $WAITED -lt 30 ]; do
    if ss -tlnp | grep -q ':8080'; then
        echo "[$TIMESTAMP] ApplicationStart: app listening on :8080 after ${WAITED}s" >> $LOG
        exit 0
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

# App never came up — print journal logs and fail the deployment
echo "[$TIMESTAMP] ApplicationStart: ERROR — app did not bind to :8080 after 30s" >> $LOG
journalctl -u my-app --no-pager -n 50 >> $LOG 2>&1 || true
exit 1
