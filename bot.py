"""
🎌 Anime Bot PRO — Aiogram 3.x
Ishga tushirish: python bot.py
"""
import asyncio
import logging
import sys
from pathlib import Path

try:
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import BotCommand
except ImportError:
    print("❌ aiogram o'rnatilmagan!")
    print(f"  {sys.executable} -m pip install -r requirements.txt")
    sys.exit(1)

try:
    from config import BOT_TOKEN, ADMIN_IDS, BASE_DIR, LOG_FILE
    from database.db import init_db
    from middlewares.register import RegisterMiddleware
    from middlewares.subscribe import SubscribeMiddleware
    from handlers import start, search, anime, admin
except ImportError as e:
    print(f"❌ Import xatosi: {e}")
    sys.exit(1)


LOG_PATH = Path(LOG_FILE)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def set_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start",   description="🏠 Asosiy menyu"),
        BotCommand(command="menu",    description="📋 Menyuni ochish"),
        BotCommand(command="help",    description="🆘 Yordam"),
    ])


async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN .env faylida yo'q!")
        sys.exit(1)

    await init_db()

    try:
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        me = await bot.get_me()
    except Exception as e:
        print(f"❌ Token xato yoki internet yo'q: {e}")
        sys.exit(1)

    dp = Dispatcher(storage=MemoryStorage())

    # Middlewarelar
    dp.message.middleware(RegisterMiddleware())
    dp.callback_query.middleware(RegisterMiddleware())
    dp.message.middleware(SubscribeMiddleware())
    dp.callback_query.middleware(SubscribeMiddleware())

    # Routerlar (tartib muhim!)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(anime.router)
    dp.include_router(search.router)

    await set_commands(bot)

    print("=" * 55)
    print(f"✅  Bot: @{me.username} ({me.first_name})")
    print(f"🆔  ID: {me.id}")
    print(f"👑  Adminlar: {ADMIN_IDS}")
    print(f"📁  Papka: {BASE_DIR}")
    print(f"📝  Log: {LOG_PATH}")
    print("=" * 55)
    print("Ctrl+C — to'xtatish")

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n⛔ Bot to'xtatildi")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
