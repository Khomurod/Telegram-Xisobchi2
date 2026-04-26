from aiogram import Bot
from aiogram.enums import ButtonStyle
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from app.utils.logger import setup_logger

logger = setup_logger("phone_prompt")

PHONE_CONTACT_TEXT = "Telefon raqamni yuborish"
PHONE_SKIP_TEXT = "O'tkazib yuborish"
PHONE_SKIPPED_VALUE = "skipped"
PHONE_PROMPT_TRANSACTION_MILESTONE = 10


def build_phone_request_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard for delayed phone number sharing."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=PHONE_CONTACT_TEXT,
                    request_contact=True,
                    style=ButtonStyle.PRIMARY,
                )
            ],
            [KeyboardButton(text=PHONE_SKIP_TEXT, style=ButtonStyle.DANGER)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Telefon raqamingizni yuboring yoki o'tkazib yuboring",
    )


def should_request_phone_prompt(phone_number: str | None, transaction_count: int) -> bool:
    """
    Ask for phone number only on the exact milestone transaction.
    Users who previously skipped are treated as missing phone and can still be prompted.
    """
    normalized = (phone_number or "").strip().lower()
    has_real_phone = bool(normalized) and normalized != PHONE_SKIPPED_VALUE
    return transaction_count == PHONE_PROMPT_TRANSACTION_MILESTONE and not has_real_phone


async def send_phone_prompt(bot: Bot, telegram_id: int) -> None:
    """Send delayed phone value-proposition message."""
    await bot.send_message(
        chat_id=telegram_id,
        text=(
            "🎉 Siz 10 ta operatsiya qo'shdingiz!\n\n"
            "📱 Telefon raqamingizni ulashing — yangi yangilanishlar va funksiyalarga "
            "boshqalardan oldin kirish imkoniyatini beramiz.\n\n"
            "Majburiy emas, istasangiz o'tkazib yuborishingiz mumkin."
        ),
        reply_markup=build_phone_request_keyboard(),
    )
    logger.info(f"Delayed phone prompt sent to user {telegram_id}")
