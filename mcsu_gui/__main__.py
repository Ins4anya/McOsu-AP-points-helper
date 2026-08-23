import sys

from nicegui import ui

from mcsu_bot.config import load_config
from mcsu_gui.app import page, prepare

GUI_PORT = 8866


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
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


if __name__ == "__main__":
    main()