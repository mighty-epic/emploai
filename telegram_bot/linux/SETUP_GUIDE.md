# Linux VPS Setup Guide for Emploai Telegram Agent

## Prerequisites
- Ubuntu 22.04+ VPS (Contabo, Hetzner, etc.)
- At least 4GB RAM, 2 vCPU, 50GB SSD
- SSH access

## 1. System Packages

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Python
sudo apt install -y python3 python3-pip python3-venv git

# Virtual display (required for PyAutoGUI and Chrome)
sudo apt install -y xvfb

# Desktop automation tools
sudo apt install -y xdotool wmctrl

# Clipboard support
sudo apt install -y xclip

# Screenshot / OCR
sudo apt install -y scrot tesseract-ocr libtesseract-dev

# Chrome browser
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# Chrome driver (for Selenium)
sudo apt install -y chromium-chromedriver || true
```

## 2. Clone and Setup

```bash
# Create a dedicated runtime user for the headed desktop session
sudo useradd --system --create-home --shell /bin/bash emploai || true

# Clone the repo
sudo git clone <your-repo-url> /opt/emploai
sudo chown -R emploai:emploai /opt/emploai
cd /opt/emploai

# Create virtual environment and install dependencies as the runtime user
sudo -u emploai python3 -m venv /opt/emploai/venv
sudo -u emploai /opt/emploai/venv/bin/pip install -r /opt/emploai/requirements.txt
sudo -u emploai /opt/emploai/venv/bin/pip install python-xlib
```

## 3. Environment Configuration

```bash
# Preferred: keep secrets outside the repo checkout
sudo mkdir -p /etc/emploai
cp .env.example /tmp/agent.env
nano /tmp/agent.env
sudo mv /tmp/agent.env /etc/emploai/agent.env
```

Required env entries:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=your_telegram_user_id

# API Keys (at least one is required)
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key
GOOGLE_API_KEY=your_key

# Platform (auto-detected, but can be forced)
# PLATFORM=linux
```

## 4. Start Virtual Display

```bash
# Start Xvfb (virtual framebuffer) on display :99
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
```

## 5. Run the Bot

```bash
cd /opt/emploai/telegram_bot
export DISPLAY=:99
export HEADLESS=false
source /opt/emploai/venv/bin/activate
python telegram_agent.py
```

## 6. Run as a Background Service (Recommended)

Create a systemd service for auto-start and persistence:

```bash
sudo nano /etc/systemd/system/emploai.service
```

Paste:
```ini
[Unit]
Description=Emploai Telegram Agent
After=network.target emploai-display.service
Requires=emploai-display.service

[Service]
Type=simple
User=emploai
Group=emploai
WorkingDirectory=/opt/emploai/telegram_bot
Environment="PLATFORM=linux"
Environment="DISPLAY=:99"
Environment="XAUTHORITY=/opt/emploai/.xauth/emploai-xauth"
Environment="HEADLESS=false"
Environment="PATH=/opt/emploai/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=-/opt/emploai/.env
EnvironmentFile=-/etc/emploai/agent.env
ExecStart=/opt/emploai/venv/bin/python telegram_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create a matching display service so Chrome, OCR, and physical desktop tools
run inside the same non-root X11 session:

```bash
sudo nano /etc/systemd/system/emploai-display.service
```

Paste:

```ini
[Unit]
Description=Emploai persistent virtual display
After=network.target

[Service]
Type=simple
User=emploai
Group=emploai
WorkingDirectory=/opt/emploai
Environment="DISPLAY_NUM=:99"
Environment="DISPLAY_GEOMETRY=1920x1080x24"
Environment="VNC_PORT=5900"
Environment="VNC_BIND_LOCALHOST=1"
Environment="XAUTH_FILE=/opt/emploai/.xauth/emploai-xauth"
ExecStart=/bin/bash /opt/emploai/deploy/vps/linux/start-display.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable emploai-display
sudo systemctl enable emploai
sudo systemctl start emploai-display
sudo systemctl start emploai

# Check status
sudo systemctl status emploai-display
sudo systemctl status emploai

# View logs
journalctl -u emploai-display -f
journalctl -u emploai -f
```

## 7. Verify Everything Works

From Telegram, send `/start` to your bot. Then test:
1. Send a text message — should get an AI response
2. Ask it to "list the files in the current directory" — tests terminal
3. Ask it to "open Chrome and go to google.com" — tests Selenium + Xvfb
4. Ask it to "take a screenshot" — tests mss + Xvfb

## Troubleshooting

### "No display" errors
Ensure `DISPLAY=:99` is set and Xvfb is running:
```bash
ps aux | grep Xvfb
```

### "Running as root without --no-sandbox" errors
The bot or display service is still running as `root`. For headed Chrome and the
extension bridge, both services must run as the same non-root user such as
`emploai`.

### PyAutoGUI fails
Install python-xlib: `pip install python-xlib`
Ensure scrot is installed: `sudo apt install scrot`

### Chrome crashes
If Selenium crashes, the agent already sets the needed browser flags. If visible
Chrome fails with a root/no-sandbox error, fix the service user instead of
adding root-only workarounds.

### OCR returns empty
Ensure tesseract is installed: `tesseract --version`

### Window tools return "unavailable"
Ensure xdotool and wmctrl are installed:
```bash
which xdotool wmctrl
```
