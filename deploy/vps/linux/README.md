# Linux VPS Deployment

This deployment keeps the Telegram agent on a persistent virtual desktop so it can:

- run headed Chrome
- take screenshots
- use OCR
- click/type via `pyautogui`
- manage windows via `xdotool` and `wmctrl`
- keep running even when you are not watching it

## Target Design

- Ubuntu 22.04/24.04 VPS
- Virtual display on `:99`
- `Xvfb` for the display server
- `openbox` for a lightweight window manager
- `x11vnc` so you can watch the same desktop remotely
- `telegram_agent.py` running on that same display

## Files

- `bootstrap.sh`: installs system packages and Python environment
- `start-display.sh`: starts the persistent GUI session on `:99`
- `emploai-display.service`: systemd unit for the display/VNC stack
- `emploai-agent.service`: systemd unit for the Telegram agent
- `browser_bridge_smoke.py`: manual live-environment bridge test for Chrome + the unpacked extension

## Expected Paths

Default assumptions:

- repo path: `/opt/emploai`
- venv path: `/opt/emploai/venv`
- run user: `root`
- display: `:99`
- VNC port: `5900`

You can change these in the systemd units before enabling them.

## Basic Flow

1. SSH into the VPS.
2. Clone the repo to `/opt/emploai`.
3. Run `deploy/vps/linux/bootstrap.sh`.
4. Copy the service files into `/etc/systemd/system/`.
5. Create `/opt/emploai/.env`.
6. Enable and start the services.

## Commands

Bootstrap:

```bash
cd /opt/emploai
bash deploy/vps/linux/bootstrap.sh
```

Install services:

```bash
sudo cp deploy/vps/linux/emploai-display.service /etc/systemd/system/
sudo cp deploy/vps/linux/emploai-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable emploai-display.service
sudo systemctl enable emploai-agent.service
sudo systemctl start emploai-display.service
sudo systemctl start emploai-agent.service
```

Check status:

```bash
systemctl status emploai-display.service
systemctl status emploai-agent.service
journalctl -u emploai-agent.service -f
```

Run a live bridge smoke test on the VPS:

```bash
systemctl stop emploai-agent.service
source /opt/emploai/venv/bin/activate
python deploy/vps/linux/browser_bridge_smoke.py --url https://open.spotify.com
systemctl start emploai-agent.service
```

This validates the extension bridge against the actual VPS desktop and Chrome session, including `browser_snapshot`.

## Remote Viewing

By default the VNC server binds to localhost only. Tunnel it over SSH:

```bash
ssh -L 5900:127.0.0.1:5900 root@<server-ip>
```

Then connect your VNC viewer to:

```text
127.0.0.1:5900
```

This attaches to the same display the agent uses. Disconnecting the viewer does not stop the display.

## Required Secrets

Add these to `/opt/emploai/.env`:

```env
TELEGRAM_BOT_TOKEN=...
ALLOWED_USER_IDS=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
PLATFORM=linux
DISPLAY=:99
HEADLESS=false
```

Use only the keys you actually need. Do not commit `.env`.
