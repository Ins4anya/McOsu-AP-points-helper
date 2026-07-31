from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "sqlite+aiosqlite:///scores_server.db"

    osu_client_id: str = ""
    osu_client_secret: str = ""
    osu_redirect_uri: str = "http://localhost:8000/auth/callback"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30

    site_url: str = "http://localhost:8000"

    @classmethod
    def from_env(cls) -> ServerConfig:
        return cls(
            host=os.getenv("HOST", cls.host),
            port=int(os.getenv("PORT", str(cls.port))),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            osu_client_id=os.getenv("OSU_CLIENT_ID", cls.osu_client_id),
            osu_client_secret=os.getenv("OSU_CLIENT_SECRET", cls.osu_client_secret),
            osu_redirect_uri=os.getenv("OSU_REDIRECT_URI", cls.osu_redirect_uri),
            jwt_secret=os.getenv("JWT_SECRET", cls.jwt_secret),
            site_url=os.getenv("SITE_URL", cls.site_url),
        )
