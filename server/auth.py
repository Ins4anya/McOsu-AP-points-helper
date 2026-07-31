from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import ServerConfig
from server.database import User, get_session

security = HTTPBearer(auto_error=False)

OSU_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
OSU_ME_URL = "https://osu.ppy.sh/api/v2/me"
OSU_AUTHORIZE_URL = "https://osu.ppy.sh/oauth/authorize"


def get_authorize_url(config: ServerConfig) -> str:
    params = (
        f"client_id={config.osu_client_id}"
        f"&redirect_uri={config.osu_redirect_uri}"
        f"&response_type=code"
        f"&scope=identify"
    )
    return f"{OSU_AUTHORIZE_URL}?{params}"


async def exchange_code(config: ServerConfig, code: str) -> dict:
    data = {
        "client_id": config.osu_client_id,
        "client_secret": config.osu_client_secret,
        "redirect_uri": config.osu_redirect_uri,
        "code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(OSU_TOKEN_URL, data=data)
        resp.raise_for_status()
        return resp.json()


async def refresh_osu_token(config: ServerConfig, refresh_token: str) -> dict:
    data = {
        "client_id": config.osu_client_id,
        "client_secret": config.osu_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(OSU_TOKEN_URL, data=data)
        resp.raise_for_status()
        return resp.json()


async def fetch_osu_user(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(OSU_ME_URL, headers=headers)
        resp.raise_for_status()
        return resp.json()


def create_jwt(config: ServerConfig, user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=config.jwt_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expires}
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def decode_jwt(config: ServerConfig, token: str) -> int | None:
    try:
        payload = jwt.decode(
            token, config.jwt_secret, algorithms=[config.jwt_algorithm]
        )
        return int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        return None


async def get_current_user(
    config: ServerConfig = Depends(ServerConfig.from_env),
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    user_id = decode_jwt(config, credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user
