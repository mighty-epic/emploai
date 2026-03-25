#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/emploai}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/venv}"
APP_USER="${APP_USER:-emploai}"
APP_GROUP="${APP_GROUP:-$APP_USER}"

export DEBIAN_FRONTEND=noninteractive

run_as_app_user() {
  local command="$1"
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u "$APP_USER" bash -lc "$command"
  else
    bash -lc "$command"
  fi
}

sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  fonts-liberation \
  git \
  openbox \
  python3 \
  python3-pip \
  python3-venv \
  scrot \
  tesseract-ocr \
  wmctrl \
  x11-utils \
  x11vnc \
  xclip \
  xdotool \
  xvfb

if ! command -v google-chrome >/dev/null 2>&1 && ! command -v google-chrome-stable >/dev/null 2>&1; then
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y google-chrome-stable
fi

if [[ "$(id -u)" -eq 0 ]]; then
  if ! id -u "$APP_USER" >/dev/null 2>&1; then
    sudo useradd --system --create-home --shell /bin/bash "$APP_USER"
  fi
  sudo mkdir -p "$REPO_DIR"
  sudo chown -R "$APP_USER:$APP_GROUP" "$REPO_DIR"
fi

run_as_app_user "python3 -m venv '$VENV_DIR'"
run_as_app_user "source '$VENV_DIR/bin/activate' && python -m pip install --upgrade pip wheel setuptools"
run_as_app_user "source '$VENV_DIR/bin/activate' && python -m pip install -r '$REPO_DIR/requirements.txt'"
run_as_app_user "source '$VENV_DIR/bin/activate' && python -m pip install python-xlib"

echo "Bootstrap complete."
echo "Repo: $REPO_DIR"
echo "Venv: $VENV_DIR"
echo "Run user: $APP_USER"
