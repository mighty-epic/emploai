# EmploAI Remote Control Plane on Ubuntu 22.04

This is the deployment path for the **public mobile control plane**.

Use this when you want:
- desktop and mobile to authenticate through a VPS
- HTTPS and WSS for cross-network access
- the phone to reach the user’s paired desktop from any network

This is **not** the older headed-X11 Telegram VPS path.

## What runs on the VPS
- FastAPI app from [remote_control_service.py](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/mobile_app/backend/remote_control_service.py)
- `nginx` reverse proxy
- TLS via Certbot or your preferred certificate setup

The VPS owns:
- account auth
- device pairing
- shared mirrored state
- realtime fan-out

The desktop still owns:
- file access
- tools
- `describe_screen` / `ocr_screen`
- cron on that machine
- actual agent execution

## Files
- [bootstrap_remote_control.sh](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/deploy/vps/linux/bootstrap_remote_control.sh)
- [remote_control.env.example](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/deploy/vps/linux/remote_control.env.example)
- [emploai-remote-control.service](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/deploy/vps/linux/emploai-remote-control.service)
- [nginx-remote-control.conf](C:/Users/Magsihim_AI/Documents/GitHub/powerful-project-collection/emploai/deploy/vps/linux/nginx-remote-control.conf)

## Assumed paths
- repo: `/opt/emploai`
- venv: `/opt/emploai/venv`
- app user: `emploai`
- runtime state: `/var/lib/emploai-remote`
- local backend bind: `127.0.0.1:8787`

## Bootstrap
```bash
cd /opt/emploai
sudo APP_USER=emploai APP_ROOT=/opt/emploai bash deploy/vps/linux/bootstrap_remote_control.sh
```

## Environment
```bash
sudo mkdir -p /etc/emploai
sudo cp deploy/vps/linux/remote_control.env.example /etc/emploai/remote-control.env
sudo nano /etc/emploai/remote-control.env
```

Minimum fields to set:
- provider key(s) you actually use
- `EMPLOAI_HOME`
- optional `EMPLO_APP_PAIRING_SECRET` if you still want the legacy local pair-start bootstrap path available

## systemd
```bash
sudo cp deploy/vps/linux/emploai-remote-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable emploai-remote-control.service
sudo systemctl start emploai-remote-control.service
sudo systemctl status emploai-remote-control.service
```

## nginx
```bash
sudo cp deploy/vps/linux/nginx-remote-control.conf /etc/nginx/sites-available/emploai-remote-control
sudo ln -sf /etc/nginx/sites-available/emploai-remote-control /etc/nginx/sites-enabled/emploai-remote-control
sudo nginx -t
sudo systemctl reload nginx
```

Then replace `your-emploai-domain.example` with your real domain and install TLS, for example:
```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-emploai-domain.example
```

## Health check
```bash
curl https://your-emploai-domain.example/api/app/health
```

## Websocket routing
The control plane has two command-routing modes:

- `EMPLOAI_REMOTE_CONTROL_ROUTING_MODE=single_process` keeps desktop command delivery in memory. Use exactly one app worker.
- `EMPLOAI_REMOTE_CONTROL_ROUTING_MODE=sqlite_broker` stores remote desktop commands in the shared `EMPLOAI_HOME` SQLite database so another worker process on the same VPS can claim and deliver them to the desktop websocket it owns.

`sqlite_broker` is for one VPS/shared-disk deployments. A multi-host cluster still needs a real external broker or load-balancer design that preserves command ownership across hosts.

The release deployment template defaults to `sqlite_broker` even when the systemd unit runs one worker, so adding more app workers on the same VPS does not silently fall back to in-memory desktop command delivery. Keep `EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS=0` for public deployments.

## Important notes
- Mobile v1 is text-first and does not expose mobile voice.
- The desktop app still needs to be configured with the same VPS URL and account credentials so its managed remote-control worker can connect outward.
- The old Linux X11/Telegram deployment path is still in the repo for legacy headed automation, but it is no longer the primary mobile architecture.
