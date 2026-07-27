import sys
import threading
from pathlib import Path

from mcsu_bot.config import load_config
from mcsu_bot_gui.main_window import App


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

    web_thread = threading.Thread(target=_run_web, daemon=True)
    web_thread.start()

    app = App(config)
    app.mainloop()


def _run_web():
    import uvicorn
    from web.server import app
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
