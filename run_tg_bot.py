#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skyrex Computers - Standalone Telegram Admin Bot Service
Запускает Telegram Admin Bot в отдельном изолированном процессе (для независимой работы от веб-сервера).
"""

import os
import sys
import asyncio
import logging
import dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("skyrex_tg_service")

# Load environment variables
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from tg_admin_bot import TelegramAdminBot

async def main():
    tg_token = os.getenv("TG_BOT_TOKEN", "").strip()
    if not tg_token:
        logger.error("TG_BOT_TOKEN is empty. Please set it in .env file.")
        sys.exit(1)

    logger.info("Initializing standalone Skyrex Telegram Admin Bot...")
    bot = TelegramAdminBot(token=tg_token)
    await bot.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Telegram Admin Bot service stopped cleanly.")
