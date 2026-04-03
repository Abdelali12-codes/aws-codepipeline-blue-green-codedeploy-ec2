#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
INSTANCE_ID=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id)

echo "[$TIMESTAMP] BeforeAllowTraffic: instance=$INSTANCE_ID" >> $LOG

# 1. Warm-up: send a few requests to the app so JIT/caches are primed
#    before real traffic hits. This avoids slow first-request latency.
echo "[$TIMESTAMP] BeforeAllowTraffic: warming up app" >> $LOG
for i in $(seq 1 5); do
    curl -sf http://localhost:8080/ > /dev/null
    curl -sf http://localhost:8080/health > /dev/null
done
echo "[$TIMESTAMP] BeforeAllowTraffic: warm-up done" >> $LOG

# 2. Final health assertion — must pass or deployment fails and rolls back
HTTP_CODE=$(curl -s -o /tmp/pre_traffic_response.json -w "%{http_code}" http://localhost:8080/health)
if [ "$HTTP_CODE" -ne 200 ]; then
    echo "[$TIMESTAMP] BeforeAllowTraffic: FAILED — /health returned HTTP $HTTP_CODE" >> $LOG
    exit 1
fi

# 3. Confirm systemd unit is active
if ! systemctl is-active --quiet my-app; then
    echo "[$TIMESTAMP] BeforeAllowTraffic: FAILED — my-app systemd unit not active" >> $LOG
    exit 1
fi

# 4. Confirm port 8080 is bound
if ! ss -tlnp | grep -q ':8080'; then
    echo "[$TIMESTAMP] BeforeAllowTraffic: FAILED — nothing listening on :8080" >> $LOG
    exit 1
fi

echo "[$TIMESTAMP] BeforeAllowTraffic: all checks passed, ready for ALB registration" >> $LOG
