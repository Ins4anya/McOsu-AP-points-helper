from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import (
    clear_token_cookie,
    create_jwt,
    exchange_code,
    fetch_osu_user,
    get_authorize_url,
    get_current_user,
    refresh_osu_token,
    set_token_cookie,
)
from server.config import ServerConfig
from server.database import User, get_session

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "oauth_state"


@router.get("/login")
async def login(config: ServerConfig = Depends(ServerConfig.from_env)):
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(get_authorize_url(config, state))
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        path="/auth",
        httponly=True,
        samesite="lax",
        secure=config.site_url.startswith("https://"),
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
    config: ServerConfig = Depends(ServerConfig.from_env),
    session: AsyncSession = Depends(get_session),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE, "")
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token_data = await exchange_code(config, code)
    osu_user = await fetch_osu_user(token_data["access_token"])

    osu_id = int(osu_user["id"])
    result = await session.execute(select(User).where(User.osu_id == osu_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            osu_id=osu_id,
            username=osu_user["username"],
            avatar_url=osu_user.get("avatar_url", ""),
            osu_access_token=token_data["access_token"],
            osu_refresh_token=token_data["refresh_token"],
        )
        session.add(user)
    else:
        user.username = osu_user["username"]
        user.avatar_url = osu_user.get("avatar_url", "")
        user.osu_access_token = token_data["access_token"]
        user.osu_refresh_token = token_data["refresh_token"]

    await session.commit()
    await session.refresh(user)

    jwt_token = create_jwt(config, user.id)
    redirect_url = f"{config.site_url}/profile"
    response = RedirectResponse(redirect_url)
    set_token_cookie(
        response,
        jwt_token,
        secure=config.site_url.startswith("https://"),
        max_age=config.jwt_expire_minutes * 60,
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/auth")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    clear_token_cookie(response)
    return response


@router.post("/refresh-token")
async def refresh_token_route(
    config: ServerConfig = Depends(ServerConfig.from_env),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        token_data = await refresh_osu_token(config, current_user.osu_refresh_token)
        current_user.osu_access_token = token_data["access_token"]
        current_user.osu_refresh_token = token_data["refresh_token"]
        await session.commit()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
