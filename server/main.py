from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.config import ServerConfig
from server.database import close_db, init_db
from server.routers import api, auth, pages

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

config = ServerConfig.from_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(config)
    yield
    await close_db()


app = FastAPI(title="McOsu AP Tracker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

app.include_router(auth.router)
app.include_router(api.router)
app.include_router(pages.router)


@app.exception_handler(401)
async def unauthorized_handler(request: Request, _):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return RedirectResponse(url="/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host=config.host, port=config.port, reload=True)
