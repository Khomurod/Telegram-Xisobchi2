from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import settings
from app.handlers import commands, voice, text

# Create bot and dispatcher
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# Register handler routers (order matters — text is catch-all, must be last)
dp.include_router(commands.router)
dp.include_router(voice.router)
dp.include_router(text.router)

