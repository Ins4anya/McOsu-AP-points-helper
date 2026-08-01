from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from server.auth import TOKEN_COOKIE_NAME, decode_jwt, get_current_user
from server.config import ServerConfig
from server.database import User


def _resolve_token(request: Request, query_token: str = "") -> str:
    return request.cookies.get(TOKEN_COOKIE_NAME) or query_token

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    token: str = Query(""),
    config: ServerConfig = Depends(ServerConfig.from_env),
):
    token = _resolve_token(request, token)
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
    token = _resolve_token(request, token)
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


@router.get("/players", response_class=HTMLResponse)
async def players_page(
    request: Request,
    token: str = Query(""),
    config: ServerConfig = Depends(ServerConfig.from_env),
):
    token = _resolve_token(request, token)
    user_id = decode_jwt(config, token) if token else None
    return templates.TemplateResponse(
        request,
        "players.html",
        {
            "request": request,
            "token": token,
            "logged_in": user_id is not None,
        },
    )


@router.get("/player/{osu_id}", response_class=HTMLResponse)
async def public_profile_page(
    request: Request,
    osu_id: int,
    token: str = Query(""),
    config: ServerConfig = Depends(ServerConfig.from_env),
):
    token = _resolve_token(request, token)
    user_id = decode_jwt(config, token) if token else None
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "token": token,
            "logged_in": user_id is not None,
            "viewing_other": True,
            "osu_id": osu_id,
        },
    )
