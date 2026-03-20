from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import settings
from app.handlers import onboarding, commands, voice, text, edit

# Create bot and dispatcher
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# Register handler routers (order matters — text is catch-all, must be last)
dp.include_router(onboarding.router)  # /start + onboarding FSM — must be first
dp.include_router(commands.router)
dp.include_router(voice.router)
dp.include_router(edit.router)   # edit/delete must come before catch-all text
dp.include_router(text.router)

