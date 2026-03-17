#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/emploai}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/venv}"

export DEBIAN_FRONTEND=noninteractive

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

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r "$REPO_DIR/requirements.txt"
python -m pip install python-xlib

echo "Bootstrap complete."
echo "Repo: $REPO_DIR"
echo "Venv: $VENV_DIR"
