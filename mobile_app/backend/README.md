# EmploAI Mobile App Backend

FastAPI backend scaffold for the additive `app` channel.

Included now:
- `/api/app/health`
- pairing endpoints
- session list/create/detail endpoints using the shared session store
- job list/detail/action endpoints using the existing scheduler
- upload endpoint scaffold
- `WS /ws/app/chat`
- `WS /ws/app/voice`
- embedded startup hook callable from `telegram_bot/telegram_agent.py`

Current status:
- additive scaffold only
- Telegram behavior remains intact
- realtime chat/voice currently return scaffold events, not the full unified agent runtime yet
