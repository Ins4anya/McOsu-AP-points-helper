from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from server.auth import decode_jwt, get_current_user
from server.config import ServerConfig
from server.database import User

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    token: str = Query(""),
    config: ServerConfig = Depends(ServerConfig.from_env),
):
    user_id = decode_jwt(config, token) if token else None
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "token": token,
            "logged_in": user_id is not None,
        },
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    token: str = Query(""),
    config: ServerConfig = Depends(ServerConfig.from_env),
):
    user_id = decode_jwt(config, token) if token else None
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "token": token,
            "logged_in": user_id is not None,
        },
    )
