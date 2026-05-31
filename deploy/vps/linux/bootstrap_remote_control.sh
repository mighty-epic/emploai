#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-emploai}"
APP_ROOT="${APP_ROOT:-/opt/emploai}"
VENV_PATH="${VENV_PATH:-$APP_ROOT/venv}"
STATE_ROOT="${STATE_ROOT:-/var/lib/emploai-remote}"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  nginx \
  git \
  build-essential \
  libgl1 \
  libglib2.0-0

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$APP_USER"
fi

mkdir -p "$APP_ROOT" "$STATE_ROOT"
chown -R "$APP_USER":"$APP_USER" "$APP_ROOT" "$STATE_ROOT"

python3 -m venv "$VENV_PATH"
"$VENV_PATH/bin/pip" install --upgrade pip wheel setuptools
"$VENV_PATH/bin/pip" install -r "$APP_ROOT/requirements.txt"

mkdir -p /etc/emploai
cat <<EOF
Remote control bootstrap complete.

Next steps:
1. Copy deploy/vps/linux/remote_control.env.example to /etc/emploai/remote-control.env
2. Fill in your secrets and paths
3. Install deploy/vps/linux/emploai-remote-control.service
4. Install deploy/vps/linux/nginx-remote-control.conf
EOF
