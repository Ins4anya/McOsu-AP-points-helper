import sys
from pathlib import Path

from nicegui import ui

from mcsu_bot.config import load_config
from mcsu_gui.app import page, prepare

GUI_PORT = 8866


def main():
    """Default: NiceGUI desktop window (native)."""
    config_path = _config_path()
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

    prepare(config)
    ui.run(
        root=page,
        window_size=(1020, 1020),
        title="McOsu AP Tracker",
        reload=False,
        dark=True,
        show=False,
        port=GUI_PORT,
    )


def main_legacy():
    """Fallback: old customtkinter GUI (kept as-is)."""
    import threading

    from mcsu_bot_gui.main_window import App

    config_path = _config_path()
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

    web_thread = threading.Thread(target=_run_web, daemon=True)
    web_thread.start()

    app = App(config)
    app.mainloop()


def _config_path() -> str:
    """Find a config.json to use.

    Order: explicit CLI arg > next to the executable > current dir > the
    project 'McOsu_bot_полигон' sibling of the executable (so a release
    build placed anywhere still uses the polygon's databases).
    """
    for arg in sys.argv[1:]:
        if not arg.startswith("-") and Path(arg).exists():
            return arg

    candidates = ["config.json"]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.insert(0, str(exe_dir / "config.json"))
        candidates.append(str(exe_dir.parent / "McOsu_bot_полигон" / "config.json"))

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return candidates[0]


def _run_web():
    import uvicorn
    from web.server import app

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    if "--legacy" in sys.argv:
        main_legacy()
    else:
        main()