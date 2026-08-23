from __future__ import annotations

import asyncio

from sqlalchemy import select

import server.database as db
from server.auth import lookup_beatmap_by_md5
from server.config import ServerConfig
from server.database import Score, close_db, init_db


async def main() -> None:
    config = ServerConfig.from_env()

    if not config.osu_client_id or not config.osu_client_secret:
        print("ERROR: OSU_CLIENT_ID / OSU_CLIENT_SECRET not set in server/.env")
        return

    await init_db(config)
    try:
        async with db._SessionLocal() as session:
            result = await session.execute(
                select(Score).where(
                    Score.beatmap_url == "",
                    Score.md5 != "",
                )
            )
            rows = list(result.scalars().all())
            if not rows:
                print("Nothing to backfill - all scores already have a link.")
                return

            by_md5: dict[str, list[Score]] = {}
            for score in rows:
                by_md5.setdefault(score.md5, []).append(score)

            resolved = 0
            not_found: list[str] = []
            total = len(by_md5)
            for i, md5 in enumerate(sorted(by_md5), start=1):
                meta = await lookup_beatmap_by_md5(config, md5)
                if meta:
                    for score in by_md5[md5]:
                        score.beatmap_url = meta["map_url"]
                        if score.beatmap_id <= 0 and meta.get("beatmap_id"):
                            score.beatmap_id = int(meta["beatmap_id"])
                        if not score.beatmap_title or score.beatmap_title == "Unknown":
                            score.beatmap_title = meta["title"]
                        if not score.stars:
                            score.stars = float(meta.get("stars") or 0.0)
                    resolved += len(by_md5[md5])
                    print(f"[{i}/{total}] resolved: {meta['map_url']}")
                else:
                    not_found.append(md5)
                    print(f"[{i}/{total}] not found: {md5}")
                await asyncio.sleep(0.2)

            await session.commit()
            print(
                f"\nDone: {resolved} score(s) got a link, "
                f"{len(not_found)} md5(s) not found."
            )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())