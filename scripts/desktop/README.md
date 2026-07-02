# Desktop Scripts

These scripts are the supported local developer startup path.

## Start

```powershell
npm start
```

Equivalent direct command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\desktop\start.ps1
```

Useful options:

- `-Fast` - reuse the existing renderer build and skip Fleet bootstrap
- `-SkipFleetBootstrap` - start without Yggdrasil setup
- `-NoInstall` - do not auto-install missing JavaScript or Python dependencies
- `-CheckOnly` - validate paths/dependency state without opening Electron

The root check command prints the same startup preflight without launching:

```powershell
npm run desktop:check
```

It reports:

- Python runtime version
- core backend Python package availability
- desktop shell dependency state
- renderer dependency state
- renderer build state

If the Python package check reports missing modules, `npm start` will install
the core backend dependencies from `requirements.txt` unless `-NoInstall` is
passed. Use `npm run setup` when you want a full dependency refresh.

## Setup

```powershell
npm run setup
```

Equivalent direct command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\desktop\setup.ps1
```

Useful options:

- `-SkipPython` - install only JavaScript dependencies
- `-SkipRendererBuild` - install dependencies without exporting the renderer
