from __future__ import annotations

import os
import sys
from pathlib import Path

from deploy.windows.release_runtime import (
    bundle_root,
    configure_process_environment,
    ensure_runtime_files,
    env_path,
    load_existing_env_values,
    needs_first_run_setup,
    print_runtime_banner,
    run_first_run_setup,
    runtime_home,
)


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

    existing = load_existing_env_values(env_file)
    force_setup = "--setup" in sys.argv[1:]
    if force_setup or needs_first_run_setup(existing):
        run_first_run_setup(home=home, env_file=env_file, existing=existing)

    sys.path.insert(0, str(root))
    telegram_bot_dir = root / "telegram_bot"
    if telegram_bot_dir.exists():
        sys.path.insert(0, str(telegram_bot_dir))
    configure_process_environment(home, env_file)
    print_runtime_banner(home)

    from telegram_bot.telegram_agent import main as telegram_main

    telegram_main()


if __name__ == "__main__":
    main()
