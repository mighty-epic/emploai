# Yggdrasil Fleet Transport

EmploAI can keep Fleet manager/worker delegation without the cloud backend by using a local Yggdrasil overlay.

## Bootstrap

The desktop start command runs Yggdrasil bootstrap best-effort:

```powershell
npm --prefix desktop_app start
```

You can run it directly:

```powershell
npm --prefix desktop_app run fleet:yggdrasil:bootstrap
```

That command downloads the official Yggdrasil release installer when needed, runs the Windows MSI, configures a small set of public peers, and starts the Yggdrasil service. Windows may show a UAC prompt because Yggdrasil installs a system service and virtual network adapter.

Check status with:

```powershell
npm --prefix desktop_app run fleet:yggdrasil:status
```

## Manager

Once Yggdrasil is running on the manager machine, create a worker pairing token:

```powershell
npm --prefix desktop_app run fleet:yggdrasil:pair
```

That command:

- verifies Yggdrasil is running and has an overlay IPv6 address
- configures the manager backend to bind on IPv6 when needed
- creates a short-lived Fleet enrollment
- prints an `emploai-yggdrasil-v1...` pairing token

## Worker

Once Yggdrasil is running on the worker machine, join with the manager token:

```powershell
npm --prefix desktop_app run fleet:yggdrasil:join -- <pairing-token>
```

That command:

- completes Fleet enrollment against the manager over the Yggdrasil URL
- writes `remote-account-session.json` with `transport.kind = "yggdrasil"`
- removes stale cloud remote-control values from the local `.env`
- starts the existing remote desktop worker relay

After that, manager Fleet tasks use the existing `fleet_run_task` websocket path.

## Notes

- No EmploAI VPS, cloud login, domain, or mobile backend is required.
- The bootstrap uses the official Yggdrasil release installer, not an EmploAI-hosted binary.
- The manager and worker both still need Windows permission to install/start the Yggdrasil service.
