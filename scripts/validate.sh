#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] ValidateService: running smoke tests" >> $LOG

# Retry up to 5 times with 3s delay — app may need a moment after start
MAX_RETRIES=5
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    HTTP_CODE=$(curl -s -o /tmp/health_response.json -w "%{http_code}" http://localhost:8080/health)
    if [ "$HTTP_CODE" -eq 200 ]; then
        echo "[$TIMESTAMP] ValidateService: /health returned 200" >> $LOG
        break
    fi
    echo "[$TIMESTAMP] ValidateService: attempt $((RETRY+1)) got HTTP $HTTP_CODE, retrying..." >> $LOG
    sleep 3
    RETRY=$((RETRY + 1))
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo "[$TIMESTAMP] ValidateService: FAILED — /health never returned 200" >> $LOG
    exit 1
fi

# Validate the response body contains expected fields
BODY=$(cat /tmp/health_response.json)
echo "[$TIMESTAMP] ValidateService: response body = $BODY" >> $LOG

if ! echo "$BODY" | grep -q '"status"'; then
    echo "[$TIMESTAMP] ValidateService: FAILED — response missing 'status' field" >> $LOG
    exit 1
fi

# Validate the root endpoint also responds
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/)
if [ "$HTTP_CODE" -ne 200 ]; then
    echo "[$TIMESTAMP] ValidateService: FAILED — / returned HTTP $HTTP_CODE" >> $LOG
    exit 1
fi

# Confirm the process is running and systemd reports it active
if ! systemctl is-active --quiet my-app; then
    echo "[$TIMESTAMP] ValidateService: FAILED — systemd unit not active" >> $LOG
    exit 1
fi

echo "[$TIMESTAMP] ValidateService: all checks passed" >> $LOG
