# EmploAI Mobile App Client

Expo/React Native client scaffold for the additive `app` channel.

Included now:
- Expo Router shell screens for Pair, Chat, Sessions, Jobs, and Settings
- Android package id `com.emploai.app`
- EAS build profiles: development, preview, production
- placeholder UI aligned to the agreed v1 scope

Next wiring step:
- hook these screens to the FastAPI backend in `mobile_app/backend/app_server.py`
- add realtime chat and voice WebSocket clients
- add QR scanning, secure token storage, and upload flows
