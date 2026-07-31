from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import (
    create_jwt,
    exchange_code,
    fetch_osu_user,
    get_authorize_url,
    get_current_user,
    refresh_osu_token,
)
from server.config import ServerConfig
from server.database import User, get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(config: ServerConfig = Depends(ServerConfig.from_env)):
    url = get_authorize_url(config)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    code: str = Query(...),
    config: ServerConfig = Depends(ServerConfig.from_env),
    session: AsyncSession = Depends(get_session),
):
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
    redirect_url = f"{config.site_url}/profile?token={jwt_token}"
    return RedirectResponse(redirect_url)


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
