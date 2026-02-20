from aiogram import Router, types
from aiogram.filters import Command
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.report import ReportService
from app.utils.logger import setup_logger

logger = setup_logger("commands")
router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Register user and show welcome message."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.get_or_create(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username,
            )

        welcome = (
            "🎙 *Xisobchi Bot*ga xush kelibsiz!\n\n"
            "Men sizning moliyaviy yordamchingizman. "
            "Ovozli xabar yuboring va men avtomatik ravishda "
            "kirim yoki chiqimingizni qayd etaman.\n\n"
            "📝 *Buyruqlar:*\n"
            "/balans — Umumiy balans\n"
            "/bugun — Bugungi operatsiyalar\n"
            "/oy — Oylik hisobot\n"
            "/hisobot — To'liq hisobot\n\n"
            "🎤 *Misol:* Ovozli xabar yuboring:\n"
            '📌 _"Ovqatga 50 ming so\'m sarfladim"_\n'
            '📌 _"Maosh oldim 5 million so\'m"_'
        )
        await message.answer(welcome, parse_mode="Markdown")
        logger.info(f"User {message.from_user.id} started the bot")

    except Exception as e:
        logger.error(f"Error in /start: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Command("balans"))
async def cmd_balance(message: types.Message):
    """Show net balance across all currencies."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)
            report = ReportService(txn_repo)
            text = await report.get_balance(user.id)
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"Balance report sent to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /balans: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Command("bugun"))
async def cmd_today(message: types.Message):
    """Show today's transactions summary."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)
            report = ReportService(txn_repo)
            text = await report.get_today_report(user.id)
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"Today report sent to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /bugun: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Command("oy"))
async def cmd_month(message: types.Message):
    """Show monthly report grouped by category."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)
            report = ReportService(txn_repo)
            text = await report.get_month_report(user.id)
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"Month report sent to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /oy: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Command("hisobot"))
async def cmd_full_report(message: types.Message):
    """Show full report: balance + monthly summary."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)
            report = ReportService(txn_repo)
            text = await report.get_full_report(user.id)
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"Full report sent to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /hisobot: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
