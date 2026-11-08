from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import ServerConfig
from server.database import User, get_session

security = HTTPBearer(auto_error=False)

TOKEN_COOKIE_NAME = "mcsu_token"

OSU_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
OSU_ME_URL = "https://osu.ppy.sh/api/v2/me"
OSU_AUTHORIZE_URL = "https://osu.ppy.sh/oauth/authorize"
OSU_BEATMAP_LOOKUP_URL = "https://osu.ppy.sh/api/v2/beatmaps/lookup"

_client_token: tuple[str, float] | None = None


def get_authorize_url(config: ServerConfig, state: str) -> str:
    params = urlencode(
        {
            "client_id": config.osu_client_id,
            "redirect_uri": config.osu_redirect_uri,
            "response_type": "code",
            "scope": "identify",
            "state": state,
        }
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


async def get_osu_client_token(config: ServerConfig) -> str:
    global _client_token
    now = time.time()
    if _client_token and now < _client_token[1]:
        return _client_token[0]

    data = {
        "client_id": config.osu_client_id,
        "client_secret": config.osu_client_secret,
        "grant_type": "client_credentials",
        "scope": "public",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(OSU_TOKEN_URL, data=data)
        resp.raise_for_status()
        token_data = resp.json()

    expires_in = int(token_data.get("expires_in", 3600))
    _client_token = (
        token_data["access_token"],
        now + expires_in - 60,
    )
    return _client_token[0]


async def lookup_beatmap_by_md5(config: ServerConfig, md5: str) -> dict | None:
    try:
        token = await get_osu_client_token(config)
        headers = {"Authorization": f"Bearer {token}"}
        params = {"checksum": md5}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                OSU_BEATMAP_LOOKUP_URL, headers=headers, params=params
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            raw = resp.json()
    except Exception:
        return None

    bmset = raw.get("beatmapset")
    if not bmset:
        return None

    return {
        "beatmap_id": raw.get("id"),
        "beatmapset_id": raw.get("beatmapset_id"),
        "title": (
            f"{bmset.get('artist', '')} - {bmset.get('title', '')} "
            f"[{raw.get('version', '')}]"
        ).strip(),
        "stars": raw.get("difficulty_rating"),
        "map_url": (
            f"https://osu.ppy.sh/beatmapsets/{raw.get('beatmapset_id', 0)}"
            f"#osu/{raw.get('id', 0)}"
        ),
    }


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


def set_token_cookie(
    response,
    token: str,
    secure: bool = False,
    max_age: int = 60 * 60 * 24 * 30,
):
    response.set_cookie(
        key=TOKEN_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def clear_token_cookie(response):
    response.delete_cookie(TOKEN_COOKIE_NAME, path="/")


async def get_current_user(
    request: Request,
    config: ServerConfig = Depends(ServerConfig.from_env),
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    token = None
    if credentials is not None:
        token = credentials.credentials
    elif request.method in ("GET", "HEAD", "OPTIONS"):
        # Cookie fallback is allowed only for safe (read-only) methods.
        # State-changing requests must present the Authorization header,
        # which a cross-origin attacker cannot set — closing the CSRF window.
        token = request.cookies.get(TOKEN_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    user_id = decode_jwt(config, token)
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
