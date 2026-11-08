import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import commands

from .config import Config
from .db_reader import read_latest_score as read_latest_score_mcsu
from .osu_api import OsuAPI, _api_score_to_osu_score, _apply_object_weights
from .pp_calculator import calculate_pp
from .embed_builder import (
    build_embed,
    build_ap_breakdown_embed,
    build_profile_embed,
    build_top_embed,
    build_best_embed,
    build_daily_embed,
    build_ranked_embed,
)
from .ap_calculator import _calculate_grade, explain_ap
from .database import Database
from .models import OsuScore, BeatmapMeta, PPResult
from .profile import calculate_profile
from .paths import ap_db_file
from .server_client import check_auth, get_ranked, get_ranked_stats, get_server_url


RANKS_TXT = Path(__file__).resolve().parent.parent / "Ranks.txt"


@dataclass
class ScoreContext:
    score: OsuScore
    meta: BeatmapMeta
    pp_result: PPResult
    ap: float
    breakdown: "APBreakdown"


class McOsuBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=config.command_prefix, intents=intents)
        self.config = config
        self.osu_api = OsuAPI(config.osu_client_id, config.osu_client_secret, config.osu_cache_dir, config.songs_dir)
        self.try_count = 0
        self.db = Database(config.ap_db_path or ap_db_file())
        self.last_scores: dict[int, ScoreContext] = {}
        self.last_messages: dict[int, ScoreContext] = {}

    async def setup_hook(self):
        self.db.connect()
        await self.add_cog(OsuCommands(self))

    async def close(self):
        self.db.close()
        await self.osu_api.close()
        await super().close()


class OsuCommands(commands.Cog):
    AP_EMOJI = "📊"

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
            if score.max_possible_combo <= 0 and pp_result.max_combo > 0:
                score.max_possible_combo = pp_result.max_combo

            breakdown = explain_ap(
                score, meta, pp_result.accuracy, pp_result.star_rating_mods, pp_result
            )
            ap = breakdown.ap
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

            context = ScoreContext(
                score=score,
                meta=meta,
                pp_result=pp_result,
                ap=ap,
                breakdown=breakdown,
            )
            self.bot.last_scores[ctx.channel.id] = context

            message = await ctx.send(embed=embed)
            self.bot.last_messages[message.id] = context
            try:
                await message.add_reaction(self.AP_EMOJI)
            except Exception as e:
                print(f"Reaction add warning: {e}")

    @commands.command(name="ap", aliases=["breakdown"])
    async def ap_breakdown(self, ctx: commands.Context):
        context = self.bot.last_scores.get(ctx.channel.id)
        if context is None:
            await ctx.send("Сначала отправьте `!rs` / `!last`, чтобы получить скор.")
            return
        embed = build_ap_breakdown_embed(context.breakdown, context.score, context.meta)
        await ctx.send(embed=embed)

    @commands.command(name="profile", aliases=["p"])
    async def profile(self, ctx: commands.Context):
        async with ctx.typing():
            try:
                profile = await asyncio.to_thread(
                    calculate_profile,
                    self.bot.config.scores_db_path,
                    self.bot.config.cfg_dir,
                    getattr(self.bot.config, "source", "mcsu"),
                )
            except Exception as e:
                await ctx.send(f"Profile error: {e}")
                return
            name = profile.player_name or self.bot.config.osu_username or "Unknown"
        embed = build_profile_embed(profile, name)
        await ctx.send(embed=embed)

    @commands.command(name="top")
    async def top(self, ctx: commands.Context, limit: int = 5):
        limit = max(1, min(limit, 10))
        async with ctx.typing():
            scores = self.bot.db.get_top_scores(limit)
            if not scores:
                await ctx.send("В базе пока нет скоров.")
                return
        embed = build_top_embed(scores, limit)
        await ctx.send(embed=embed)

    @commands.command(name="best")
    async def best(self, ctx: commands.Context):
        async with ctx.typing():
            row = self.bot.db.get_best_score()
            if row is None:
                await ctx.send("В базе пока нет скоров.")
                return
        embed = build_best_embed(row)
        await ctx.send(embed=embed)

    @commands.command(name="daily")
    async def daily(self, ctx: commands.Context):
        async with ctx.typing():
            now = datetime.now()
            start = datetime(now.year, now.month, now.day)
            end = start + timedelta(days=1)
            summary = self.bot.db.get_daily_summary(
                int(start.timestamp()), int(end.timestamp())
            )
        embed = build_daily_embed(summary, start.strftime("%d.%m.%Y"))
        await ctx.send(embed=embed)

    @commands.command(name="rank", aliases=["ranked"])
    async def rank(self, ctx: commands.Context):
        async with ctx.typing():
            server_url = get_server_url()
            if not server_url or not check_auth(server_url):
                await ctx.send(
                    "Нет входа на сервер — войдите через GUI (Control → Server Sync → Login via osu!)."
                )
                return

            ok, stats = get_ranked_stats(server_url)
            if not ok:
                await ctx.send(f"Сервер недоступен: {stats}")
                return

            if not isinstance(stats, dict) or not stats.get("enabled", False):
                await ctx.send("Режим Ranked выключен на сервере.")
                return

            if not stats.get("total_settled"):
                await ctx.send("Пока нет завершённых заданий.")
                return

            active = None
            ok2, state = get_ranked(server_url)
            if ok2 and isinstance(state, dict):
                active = state.get("active")

            embed = build_ranked_embed(
                stats, active=active, display_name=ctx.author.display_name
            )
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if payload.emoji.name != self.AP_EMOJI:
            return
        context = self.bot.last_messages.get(payload.message_id)
        if context is None:
            return
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
            user = payload.member or await self.bot.fetch_user(payload.user_id)
            await message.remove_reaction(payload.emoji, user)
        except Exception as e:
            print(f"Reaction cleanup warning: {e}")
        embed = build_ap_breakdown_embed(context.breakdown, context.score, context.meta)
        await channel.send(embed=embed)


async def run_bot(config: Config):
    bot = McOsuBot(config)
    async with bot:
        await bot.start(config.discord_token)
