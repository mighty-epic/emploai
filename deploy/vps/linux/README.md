# Linux VPS Deployment

This deployment keeps the Telegram agent on a persistent virtual desktop so it can:

- run headed Chrome
- take screenshots
- use OCR
- click/type via X11-native `xdotool`
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
- `desktop_ocr_click_smoke.py`: manual live-environment test for Linux screenshot/OCR/click on the virtual desktop

## Expected Paths

Default assumptions:

- repo path: `/opt/emploai`
- venv path: `/opt/emploai/venv`
- run user: `emploai`
- display: `:99`
- VNC port: `5900`

You can change these in the systemd units before enabling them.
The agent and display services must run as the same non-root user for headed
Chrome and the extension bridge to work reliably.
The agent service accepts both `/etc/emploai/agent.env` and
`/opt/emploai/.env` so newer and older VPS installs both work.

## Basic Flow

1. SSH into the VPS.
2. Clone the repo to `/opt/emploai`.
3. Run `deploy/vps/linux/bootstrap.sh` with `APP_USER=emploai`.
4. Copy the service files into `/etc/systemd/system/`.
5. Create `/etc/emploai/agent.env` (preferred) or `/opt/emploai/.env`.
6. Enable and start the services.

## Commands

Bootstrap:

```bash
cd /opt/emploai
sudo APP_USER=emploai bash deploy/vps/linux/bootstrap.sh
```

If the `emploai` user does not exist yet, the bootstrap script will create it
and chown `/opt/emploai` so the bot can write logs, screenshots, and runtime
state under the same non-root account that owns the X11 session.

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

Run a live desktop OCR/click smoke test on the VPS:

```bash
source /opt/emploai/venv/bin/activate
DISPLAY=:99 python deploy/vps/linux/desktop_ocr_click_smoke.py
```

This opens a controlled Chrome app window on the VPS desktop, OCRs the button text, clicks it with `xdotool`, and verifies the page changed to `CLICK CONFIRMED`.

## Remote Viewing

By default the VNC server binds to localhost only. Tunnel it over SSH:

```bash
ssh -L 5900:127.0.0.1:5900 <your-admin-user>@<server-ip>
```

Then connect your VNC viewer to:

```text
127.0.0.1:5900
```

This attaches to the same display the agent uses. Disconnecting the viewer does not stop the display.

## Required Secrets

Add these to `/etc/emploai/agent.env` (preferred) or `/opt/emploai/.env`:

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
