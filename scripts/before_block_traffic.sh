#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
INSTANCE_ID=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] BeforeBlockTraffic: instance=$INSTANCE_ID" >> $LOG

# Signal the app to stop accepting new requests by creating the draining flag.
# The /health endpoint returns 503 when this file exists, which causes the
# ALB to stop routing NEW requests to this instance before deregistration.
touch /var/www/my-app/draining

# Wait up to 20s for active connections on port 8080 to finish.
# iproute2 (ss) is installed on Ubuntu by default.
WAITED=0
while [ $WAITED -lt 20 ]; do
    ACTIVE=$(ss -tn state established '( dport = :8080 or sport = :8080 )' 2>/dev/null | grep -c ESTAB || true)
    echo "[$TIMESTAMP] active connections: $ACTIVE" >> $LOG
    [ "$ACTIVE" -eq 0 ] && break
    sleep 2
    WAITED=$((WAITED + 2))
done

echo "[$TIMESTAMP] BeforeBlockTraffic: done, waited=${WAITED}s, remaining connections=$ACTIVE" >> $LOG
