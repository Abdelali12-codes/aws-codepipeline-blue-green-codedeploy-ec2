#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
APP_DIR=/var/www/my-app
VENV=/var/www/my-app-venv

echo "[$TIMESTAMP] AfterInstall: configuring installed files" >> $LOG

# Set correct permissions
chmod -R 755 "$APP_DIR"
chmod +x "$APP_DIR/main.py"
chown -R ubuntu:ubuntu "$APP_DIR"

# Install app-level requirements into the venv if present
if [ -f "$APP_DIR/requirements.txt" ]; then
    "$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
    echo "[$TIMESTAMP] AfterInstall: installed requirements.txt" >> $LOG
fi

# Write systemd unit — uses venv python so all dependencies are available
cat > /etc/systemd/system/my-app.service << EOF
[Unit]
Description=My Flask App
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/python3 $APP_DIR/main.py
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/my-app.log
StandardError=append:/var/log/my-app.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable my-app

echo "[$TIMESTAMP] AfterInstall: systemd unit written and enabled" >> $LOG
