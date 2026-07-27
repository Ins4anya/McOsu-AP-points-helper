import io
import logging
import subprocess
import threading


def free_port(port: int):
    """Kill any *other* process listening on the given TCP port."""
    import os

    our_pid = str(os.getpid())
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit() and pid != our_pid:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True,
                    )
    except Exception:
        pass


class _OutputStream(io.StringIO):
    """Redirect writes to both internal buffer and a callback."""

    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def write(self, s):
        if s.strip():
            self._cb(s.strip())
        return super().write(s)


class ProcessWorker:
    def __init__(self, on_output=None, on_started=None, on_stopped=None):
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self.on_output = on_output or (lambda x: None)
        self.on_started = on_started or (lambda: None)
        self.on_stopped = on_stopped or (lambda: None)

    @property
    def is_running(self) -> bool:
        return self._running

    def start_bot(self, config):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_bot, args=(config,), daemon=True
        )
        self._thread.start()

    def start_web(self, config):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_web, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        self.on_stopped()

    def _run_bot(self, config):
        import asyncio

        self.on_output("Starting Discord bot...")
        try:
            from mcsu_bot.bot import McOsuBot

            async def _run():
                bot = McOsuBot(config)
                async with bot:
                    self.on_started()

                    async def _waiter():
                        while not self._stop_event.is_set():
                            await asyncio.sleep(0.3)
                        await bot.close()

                    asyncio.create_task(_waiter())
                    await bot.start(config.discord_token)

            asyncio.run(_run())
        except Exception as e:
            self.on_output(f"Bot error: {e}")
            self._running = False
            self.on_stopped()

    def _run_web(self):
        import asyncio
        import uvicorn
        from web.server import app

        self.on_output("Starting web server on :8080...")

        # Redirect uvicorn log output to the console
        log_stream = _OutputStream(self.on_output)
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.propagate = False

        try:

            async def _run():
                cfg = uvicorn.Config(
                    app, host="0.0.0.0", port=8080, log_level="info",
                    log_config=None,
                )
                server = uvicorn.Server(cfg)

                async def _waiter():
                    while not self._stop_event.is_set():
                        await asyncio.sleep(0.3)
                    server.should_exit = True

                asyncio.create_task(_waiter())
                self.on_started()
                await server.serve()

            asyncio.run(_run())
        except Exception as e:
            self.on_output(f"Web server error: {e}")
            self._running = False
            self.on_stopped()
