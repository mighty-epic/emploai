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
# Clone the repo
git clone <your-repo-url> ~/emploai
cd ~/emploai

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Additional Linux-specific packages
pip install python-xlib
```

## 3. Environment Configuration

```bash
# Copy and edit .env
cp .env.example .env
nano .env
```

Required `.env` entries:
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
cd ~/emploai/telegram_bot
export DISPLAY=:99
source ~/emploai/venv/bin/activate
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
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/emploai/telegram_bot
Environment="DISPLAY=:99"
Environment="PATH=/root/emploai/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac &
ExecStart=/root/emploai/venv/bin/python telegram_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable emploai
sudo systemctl start emploai

# Check status
sudo systemctl status emploai

# View logs
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

### PyAutoGUI fails
Install python-xlib: `pip install python-xlib`
Ensure scrot is installed: `sudo apt install scrot`

### Chrome crashes
Add `--no-sandbox --disable-gpu` flags. These are already set in the agent's Selenium config.

### OCR returns empty
Ensure tesseract is installed: `tesseract --version`

### Window tools return "unavailable"
Ensure xdotool and wmctrl are installed:
```bash
which xdotool wmctrl
```
