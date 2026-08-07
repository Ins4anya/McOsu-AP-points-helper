import os
from pathlib import Path

import discord
from discord.ext import commands

from .config import Config
from .db_reader import read_latest_score as read_latest_score_mcsu
from .osu_api import OsuAPI, _api_score_to_osu_score, _apply_object_weights
from .pp_calculator import calculate_pp
from .embed_builder import build_embed
from .ap_calculator import calculate_ap, _calculate_grade
from .database import Database


RANKS_TXT = Path(__file__).resolve().parent.parent / "Ranks.txt"


class McOsuBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=config.command_prefix, intents=intents)
        self.config = config
        self.osu_api = OsuAPI(config.osu_client_id, config.osu_client_secret, config.osu_cache_dir, config.songs_dir)
        self.try_count = 0
        self.db = Database(config.ap_db_path or (Path(__file__).resolve().parent.parent / "scores_ap.db"))

    async def setup_hook(self):
        self.db.connect()
        await self.add_cog(OsuCommands(self))

    async def close(self):
        self.db.close()
        await self.osu_api.close()
        await super().close()


class OsuCommands(commands.Cog):
    def __init__(self, bot: McOsuBot):
        self.bot = bot

    @commands.command(name="rs", aliases=["last"])
    async def last_score(self, ctx: commands.Context):
        async with ctx.typing():
            source = getattr(self.bot.config, "source", "mcsu")

            if source == "api":
                username = self.bot.config.osu_username
                if not username:
                    await ctx.send("No osu! username configured. Set 'osu_username' in config.json.")
                    return
                try:
                    raw_scores = await self.bot.osu_api.get_recent_scores(username)
                except Exception as e:
                    await ctx.send(f"osu! API error: {e}")
                    return
                if not raw_scores:
                    await ctx.send("No recent scores found.")
                    return
                api_score = raw_scores[0]
                score = _api_score_to_osu_score(api_score)

                beatmap_id = api_score.get("beatmap", {}).get("id")
                if not beatmap_id:
                    await ctx.send("No beatmap ID in API response.")
                    return
                meta = await self.bot.osu_api.lookup_beatmap_by_id(beatmap_id)
                if meta is None:
                    await ctx.send("Beatmap not found on osu! servers.")
                    return
            else:
                try:
                    score = read_latest_score_mcsu(self.bot.config.scores_db_path)
                except Exception as e:
                    await ctx.send(f"Failed to read scores.db: {e}")
                    return

                try:
                    meta = await self.bot.osu_api.lookup_beatmap(score.beatmap_md5)
                except Exception as e:
                    await ctx.send(f"osu! API error: {e}")
                    return

                if meta is None:
                    await ctx.send(
                        f"Beatmap with MD5 `{score.beatmap_md5}` not found — "
                        "not on osu! servers and no matching .osu file in local Songs folder."
                    )
                    return

            try:
                osu_file = await self.bot.osu_api.download_beatmap_file(
                    meta.beatmap_id or 0, meta.beatmapset_id or 0, score.beatmap_md5
                )
            except Exception as e:
                await ctx.send(f"Failed to download .osu file: {e}")
                return

            try:
                pp_result = calculate_pp(osu_file, score)
            except Exception as e:
                await ctx.send(f"Failed to calculate PP: {e}")
                return

            meta = _apply_object_weights(meta, osu_file)

            ap = calculate_ap(score, meta, pp_result.accuracy, pp_result.star_rating_mods, pp_result)
            total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
            grade = _calculate_grade(score.count300, total_hits, score.count50, score.count_miss, score.mods)
            dupe = False
            try:
                inserted = self.bot.db.insert_score(score, meta, pp_result.accuracy, grade, ap)
                if not inserted:
                    dupe = True
            except Exception as e:
                print(f"DB insert warning: {e}")

            self.bot.try_count += 1
            embed = build_embed(score, meta, pp_result, ap=ap, try_number=self.bot.try_count, ranks_txt=RANKS_TXT)
            if dupe:
                embed.set_footer(text=f"Duplicate — not saved  •  Try #{self.bot.try_count}", icon_url=None)
                embed.timestamp = discord.utils.utcnow()
            await ctx.send(embed=embed)


async def run_bot(config: Config):
    bot = McOsuBot(config)
    async with bot:
        await bot.start(config.discord_token)
