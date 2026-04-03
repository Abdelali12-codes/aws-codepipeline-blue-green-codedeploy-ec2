#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
INSTANCE_ID=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id)
# DEPLOYMENT_ID is injected by CodeDeploy as an environment variable
DEPLOYMENT_ID="${DEPLOYMENT_ID:-unknown}"

echo "[$TIMESTAMP] AfterAllowTraffic: instance=$INSTANCE_ID deployment=$DEPLOYMENT_ID" >> $LOG

# 1. Confirm the app is still healthy after ALB registration
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health)
if [ "$HTTP_CODE" -ne 200 ]; then
    # Non-fatal: traffic has already shifted, failing here won't roll back.
    # Log the warning and let CloudWatch alarms catch it.
    echo "[$TIMESTAMP] AfterAllowTraffic: WARNING — /health returned HTTP $HTTP_CODE" >> $LOG
fi

# 2. Write a deployment marker — useful for debugging which version
#    is running on each instance via SSM or direct file inspection
cat > /var/www/my-app/deployment.txt << EOF
deployment_id=$DEPLOYMENT_ID
instance_id=$INSTANCE_ID
deployed_at=$TIMESTAMP
EOF
chown ubuntu:ubuntu /var/www/my-app/deployment.txt
echo "[$TIMESTAMP] AfterAllowTraffic: wrote deployment marker" >> $LOG

# 3. Clean up the backup created in BeforeInstall — deployment succeeded
rm -rf /var/www/my-app-backup
echo "[$TIMESTAMP] AfterAllowTraffic: removed backup" >> $LOG

# 4. Rotate deploy log if it exceeds 10MB to prevent disk fill
LOG_SIZE=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
if [ "$LOG_SIZE" -gt 10485760 ]; then
    mv "$LOG" "${LOG}.old"
    echo "[$TIMESTAMP] log rotated" > "$LOG"
fi

echo "[$TIMESTAMP] AfterAllowTraffic: green instance is live and serving traffic" >> $LOG
