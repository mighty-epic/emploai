#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-:99}"
DISPLAY_GEOMETRY="${DISPLAY_GEOMETRY:-1920x1080x24}"
VNC_PORT="${VNC_PORT:-5900}"
VNC_BIND_LOCALHOST="${VNC_BIND_LOCALHOST:-1}"
XAUTH_FILE="${XAUTH_FILE:-${HOME:-/tmp}/.cache/emploai/xauth}"

export DISPLAY="$DISPLAY_NUM"
export XAUTHORITY="$XAUTH_FILE"

mkdir -p "$(dirname "$XAUTHORITY")"
touch "$XAUTHORITY"
chmod 600 "$XAUTHORITY"

if ! pgrep -u "$(id -u)" -f "Xvfb $DISPLAY_NUM" >/dev/null 2>&1; then
  Xvfb "$DISPLAY_NUM" -screen 0 "$DISPLAY_GEOMETRY" -ac +extension RANDR &
  sleep 2
fi

if ! pgrep -u "$(id -u)" -f "openbox" >/dev/null 2>&1; then
  openbox >/tmp/emploai-openbox.log 2>&1 &
  sleep 1
fi

X11VNC_ARGS=(
  -display "$DISPLAY_NUM"
  -forever
  -shared
  -rfbport "$VNC_PORT"
  -xkb
  -noxrecord
  -noxfixes
  -noxdamage
)

if [[ "$VNC_BIND_LOCALHOST" == "1" ]]; then
  X11VNC_ARGS+=(-localhost)
fi

exec x11vnc \
  "${X11VNC_ARGS[@]}"
