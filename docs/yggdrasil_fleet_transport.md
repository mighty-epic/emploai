# Yggdrasil Fleet Transport

EmploAI connects computers directly through Yggdrasil. There is no EmploAI account, hosted relay, or separate Remote surface.

## Connect Two Computers

On the manager computer:

1. Start EmploAI and open **Fleet**.
2. Under **On the manager**, enter a recognizable name for the other computer.
3. Select **Create & Copy Connection Code**.
4. Approve the Windows administrator prompt only if Yggdrasil needs to be installed or started.

On the other computer:

1. Start EmploAI and open **Fleet**.
2. Under **On the other desktop**, enter this computer's name.
3. Paste the complete code from the manager.
4. Select **Connect This Computer** and approve the Windows prompt if shown.

The code is single-use and expires after 30 minutes by default. A completed connection is saved locally and reconnects after restarts.

## Connect Several Computers

Return to the same manager computer and create a new code for each additional computer. Paste each code once on its intended computer. All connected computers then appear under **Computers in this Fleet** on that manager.

## What Pairing Does

Pairing creates a computer link only. It does not create a worker and does not copy or synchronize:

- chats or chat history
- manager or worker identities
- settings or provider state
- files, workspaces, sidebars, or automations
- screenshots, mouse input, or keyboard input

The manager may send a delegation message to the other computer's local manager agent or to a specifically named local worker. The paired computer returns delegation status, reports, and permission decisions. Agent sessions used to perform a delegation remain private on that computer.

## Permissions and Workers

The paired computer owns three connection permissions in Fleet:

- delegate to its local manager agent
- delegate to its existing local workers
- create a new local worker there

The manager may request a change, but the paired computer must approve it. Creating a worker is explicit and creates that worker only on the paired computer. Its name can then be used as a delegation target; its identity is not cloned back to the manager.

If a computer is online but shows **Update required**, update and restart EmploAI on that computer. Controls unlock automatically after it reports the current permission handshake; the Yggdrasil connection does not need to be recreated.

## Command-Line Alternative

The desktop flow above is recommended. These commands are useful for troubleshooting or a headless Windows computer.

Prepare and check Yggdrasil on both computers:

```powershell
npm run fleet:yggdrasil:bootstrap
npm run fleet:yggdrasil:status
```

Create one code on the manager:

```powershell
npm run fleet:yggdrasil:pair
```

Join on the other computer:

```powershell
npm run fleet:yggdrasil:join -- <pairing-token>
```

To save the connection without starting its durable relay immediately:

```powershell
python -m desktop_runtime.backend fleet-yggdrasil-join <pairing-token> --no-start-relay
```

Start that relay later:

```powershell
python -m desktop_runtime.backend run-remote-control-worker
```

The final command name is retained for compatibility; it runs the paired-computer relay and does not turn the computer itself into a worker.

## Notes

- The bootstrap uses the official Yggdrasil Windows installer.
- Windows administrator permission is needed only to install or start the Yggdrasil system service and network adapter.
- Connection codes contain a one-time enrollment secret. Do not post or reuse them.
