from __future__ import annotations

import os
import sys
from pathlib import Path

from desktop_runtime.config import (
    bundle_root,
    configure_process_environment,
    ensure_runtime_files,
    env_path,
    load_existing_env_values,
    needs_versioned_setup,
    open_extension_directory,
    print_runtime_banner,
    run_first_run_setup,
    runtime_home,
)
from desktop_runtime.update import maybe_install_update


def _set_console_title() -> None:
    if os.name != "nt":
        return
    try:
        os.system("title EmploAI Beta")
    except Exception:
        pass


def main() -> None:
    _set_console_title()

    root = bundle_root()
    home = runtime_home()
    env_file = env_path(home)
    ensure_runtime_files(home, root)

    if "--open-extension-dir" in sys.argv[1:]:
        opened = open_extension_directory(home)
        print(f"Opened extension folder: {opened}")
        return

    existing = load_existing_env_values(env_file)
    force_setup = "--setup" in sys.argv[1:]
    if force_setup or needs_versioned_setup(existing, home=home, source_root=root):
        run_first_run_setup(home=home, env_file=env_file, source_root=root, existing=existing)

    sys.path.insert(0, str(root))
    telegram_bot_dir = root / "telegram_bot"
    if telegram_bot_dir.exists():
        sys.path.insert(0, str(telegram_bot_dir))
    configure_process_environment(home, env_file)
    print_runtime_banner(home)

    restart_executable = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
    if maybe_install_update(home, root, args=set(sys.argv[1:]), restart_executable=restart_executable):
        return

    from telegram_bot.telegram_agent import main as telegram_main

    telegram_main()


if __name__ == "__main__":
    main()
