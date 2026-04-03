#!/bin/bash
set -e

LOG=/var/log/my-app-deploy.log
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
APP_DIR=/var/www/my-app
BACKUP_DIR=/var/www/my-app-backup

echo "[$TIMESTAMP] BeforeInstall: starting pre-install tasks" >> $LOG

# Update apt index and install dependencies
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv iproute2 curl

echo "[$TIMESTAMP] BeforeInstall: installed system packages" >> $LOG

# Create a virtualenv for the app to isolate dependencies
if [ ! -d /var/www/my-app-venv ]; then
    python3 -m venv /var/www/my-app-venv
    echo "[$TIMESTAMP] BeforeInstall: created virtualenv" >> $LOG
fi

# Install flask into the venv
/var/www/my-app-venv/bin/pip install --quiet flask

# Back up the current version for manual rollback if needed
if [ -d "$APP_DIR" ]; then
    rm -rf "$BACKUP_DIR"
    cp -r "$APP_DIR" "$BACKUP_DIR"
    echo "[$TIMESTAMP] BeforeInstall: backed up current version to $BACKUP_DIR" >> $LOG
fi

mkdir -p "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"

echo "[$TIMESTAMP] BeforeInstall: done" >> $LOG
