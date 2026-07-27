import asyncio
import sys

from .config import load_config
from .bot import run_bot


def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.json"

    config = load_config(config_path)

    if not config.discord_token or config.discord_token == "ВАШ_DISCORD_BOT_TOKEN":
        print("ERROR: Заполните discord_token в config.json")
        print("Получите токен: https://discord.com/developers/applications")
        sys.exit(1)

    if not config.osu_client_id or config.osu_client_id == "ВАШ_OSU_CLIENT_ID":
        print("ERROR: Заполните osu_client_id и osu_client_secret в config.json")
        print("Получите: https://osu.ppy.sh/home/account/edit#new-oauth-application")
        sys.exit(1)

    asyncio.run(run_bot(config))


if __name__ == "__main__":
    main()
