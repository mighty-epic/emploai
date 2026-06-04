# EmploAI Marketing Copy & Social Media Drafts

This file contains the finalized marketing copy for the initial launch of EmploAI across various social media platforms.

---

## 1. Twitter / X Threads

### Post 1: The Hook (Core Positioning)
> Chatbots talk. Agentic loops execute.
>
> Meet EmploAI: An open-source, desktop-native agentic system that accepts tasks over Telegram or an Electron shell and runs them on a live machine using LLMs, Selenium, and OS automation.
>
> 🧵 Here is how it works under the hood:
>
> [Insert short video/GIF of terminal + browser execution]

### Post 2: Solving the Browser Bot-Detection Problem
> 1/ Standalone Selenium agents break on modern apps or trigger heavy bot-detection.
>
> EmploAI handles this with a custom WebSocket bridge directly to your *real* Chrome session.
>
> This lets the agent leverage your logged-in states & active tabs securely.

### Post 3: Element Referencing (No Coordinate Guessing)
> 2/ Instead of guessing screen coordinates, EmploAI builds ARIA-style accessibility snapshots.
>
> The agent interacts with stable element references (e.g. `[ref=12]`) for navigation, clicks, option selection, and typing. Bulletproof flow execution.

### Post 4: Observability & Memory
> 3/ Black-box agents are impossible to debug.
>
> EmploAI preserves full observability:
> - Screen captures & Tesseract OCR fallback
> - Context compression to manage long conversations
> - Transparent memory stored in plain Markdown files (`MEMORY.md`)

### Post 5: Multi-Machine Hub
> 4/ EmploAI isn't just a local script.
>
> Deploy it on a Linux VPS, run background workers as systemd services, schedule cron tasks, and trigger/monitor runs from your phone via Telegram.
>
> 💻 Get started & host it yourself:
> https://github.com/heygen-com/emploai

---

## 2. LinkedIn Post

### The Pitch: The Shift from Chat to Action
> The next phase of generative AI isn't conversational text—it's agentic execution.
>
> But giving an LLM direct control of a machine raises real systems and security challenges. We built **EmploAI** as an open-source, production-ready framework to address this head-on.
>
> EmploAI connects LLM reasoning (OpenAI, Anthropic, Gemini) with a rich, controlled tool surface to execute complex, long-running computer tasks.
>
> **Core Architecture:**
> 1. 🌐 **Chromium Extension Bridge**: A WebSocket layer linking the agent directly to your active browser session, bypassing bot detection and retaining active session auth.
> 2. 🖥️ **Desktop Control Fallback**: PIL screen captures, Tesseract OCR, and keyboard/mouse emulation (using PyAutoGUI on Windows or xdotool/wmctrl on Linux virtual frames).
> 3. 📂 **Transparent State & Memory**: Open Markdown files (`MEMORY.md` & daily logs) that make the agent's long-term recall and context fully auditable.
> 4. 📱 **Multi-channel Control**: A voice-first native Electron app for local machine automation, alongside a Telegram bot interface for VPS control and recurring cron jobs.
>
> Whether you need to run background research, manage files, or automate browser workflows, EmploAI is built to keep execution secure, visible, and continuous.
>
> 👉 Clone the repo and start building: [GitHub link]
>
> #AI #ArtificialIntelligence #SoftwareEngineering #OpenSource #Productivity Automation #CloudComputing

---

## 3. Reddit Post (r/LocalLLaMA & r/selfhosted)

### Title: Show r/LocalLLaMA: EmploAI - Open-Source voice-first Desktop Agent with Telegram/VPS control and Chrome Extension Bridge

> Hey everyone,
>
> We've been working on **EmploAI**, an agentic computer-control system that connects local/cloud LLMs with native OS, terminal, and browser tools. It's fully open-source and built for persistent, long-running execution (on a local machine or a remote headless VPS).
>
> ### Why we built it:
> Giving an LLM direct terminal execution is often too loose, and headless Selenium browsers quickly fail on sites with modern bot protection (or require manual authentication bypasses). We wanted a system that was **observable**, **auditable**, and had **multiple fallback control channels** depending on the environment.
>
> ### Key Architecture Features:
>
> 1. **Chrome Extension WebSocket Bridge**: Instead of just using standard Selenium, we built a WebSocket-based Chrome extension bridge. The agent can hook directly into your real, active browser session. This means it inherits your active logins, cookies, and profiles, and easily navigates modern web apps without getting blocked.
>
> 2. **ARIA-Style Browser Snapshots**: When automating the browser, we compile the page DOM into a simplified accessibility/ARIA tree with ref tags (e.g. `[ref=4]`). The model interacts with these references instead of raw HTML or raw screen coordinates, making clicking and typing highly stable.
>
> 3. **Desktop Fallback (OCR & Keyboard/Mouse)**: If DOM-level controls fail (or the agent needs to click something outside the browser), it falls back to capturing the screen (`mss` / `scrot`) and running Tesseract OCR to read text. It then interacts via coordinate-based input (`pyautogui` on Windows or `xdotool` on Linux).
>
> 4. **Human-Inspectable Memory**: No vector database black box. The agent maintains long-term preferences in a plain `MEMORY.md` file and dumps daily logs in markdown. You can read, audit, and rewrite its memory at any time.
>
> 5. **Dual Interface**:
>    - **Local**: A voice-first native Electron app. Record your task via microphone, stream it to a local Whisper instance, and the Electron shell bootstraps the execution directly.
>    - **Remote**: A fully secured Telegram bot wrapper. Allows you to check status, trigger runs, schedule recurring cron tasks, and view screenshots on a headless VPS in the background.
>
> ### How to run it:
> The project runs on Windows and Linux (with headed or headless virtual displays via Xvfb).
>
> 1. Clone the repo and install dependencies:
>    ```bash
>    git clone https://github.com/heygen-com/emploai.git
>    cd emploai
>    pip install -r requirements.txt
>    ```
> 2. Setup your `.env` (add OpenAI/Anthropic/Gemini keys and your Telegram bot token).
> 3. Launch the Telegram bot worker:
>    ```bash
>    cd telegram_bot
>    python telegram_agent.py
>    ```
> 4. To run the desktop app, build the client and boot Electron:
>    ```bash
>    cd desktop_app
>    npm install
>    npm run start
>    ```
>
> Check out the repo and let us know what you think:
> https://github.com/heygen-com/emploai
>
> Feedbacks, issues, and PR contributions are highly welcome!
