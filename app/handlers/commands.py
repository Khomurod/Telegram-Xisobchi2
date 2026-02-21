import csv
import io
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from app.database.connection import async_session
from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.report import ReportService
from app.constants import CATEGORY_EMOJI
from app.utils.formatting import format_amount
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
            "Ovozli xabar yoki matn yuboring va men avtomatik ravishda "
            "kirim yoki chiqimingizni qayd etaman.\n\n"
            "📝 *Buyruqlar:*\n"
            "/balans — Umumiy balans\n"
            "/bugun — Bugungi operatsiyalar\n"
            "/hafta — Haftalik hisobot\n"
            "/oy — Oylik hisobot\n"
            "/hisobot — To'liq hisobot\n"
            "/tarix — ✏️ Operatsiyalarni ko'rish va tahrirlash\n"
            "/bekor — Oxirgi operatsiyani bekor qilish\n"
            "/export — CSV fayl sifatida eksport\n"
            "/yordam — Barcha buyruqlar\n\n"
            "🎤 *Misol:* Ovozli xabar yuboring:\n"
            '📌 _"Ovqatga 50 ming so\'m sarfladim"_\n'
            '📌 _"Maosh oldim 5 million so\'m"_\n\n'
            "💬 *Matn:* Yozib ham yuborishingiz mumkin:\n"
            '📌 _"transport 20 ming"_\n'
            '📌 _"kirim 3 million maosh"_'
        )
        await message.answer(welcome, parse_mode="Markdown")
        logger.info(f"User {message.from_user.id} started the bot")

    except Exception as e:
        logger.error(f"Error in /start: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Command("yordam"))
async def cmd_help(message: types.Message):
    """Show help with all available commands."""
    help_text = (
        "📖 *Yordam — Xisobchi Bot*\n\n"
        "🎤 *Ovozli xabar* yuborib operatsiya qo'shing:\n"
        '  _"Ovqatga 50 ming so\'m sarfladim"_\n'
        '  _"Maosh oldim 5 million so\'m"_\n\n'
        "💬 *Matn* yozib ham qo'shishingiz mumkin:\n"
        '  _"transport 20 ming"_\n'
        '  _"kirim 3 million maosh"_\n\n'
        "📝 *Buyruqlar:*\n"
        "/balans — 💰 Umumiy balans\n"
        "/bugun — 📊 Bugungi operatsiyalar\n"
        "/hafta — 📅 Oxirgi 7 kunlik hisobot\n"
        "/oy — 📅 Oylik hisobot\n"
        "/hisobot — 📋 To'liq hisobot\n"
        "/tarix — ✏️ Oxirgi operatsiyalarni ko'rish, tahrirlash yoki o'chirish\n"
        "/bekor — ↩️ Oxirgi operatsiyani bekor qilish\n"
        "/export — 📤 CSV fayl sifatida eksport\n"
        "/yordam — 📖 Shu yordam sahifasi\n\n"
        "📂 *Kategoriyalar:*\n"
        "🍽 Oziq-ovqat | 🚕 Transport | 🏠 Uy-joy\n"
        "💊 Sog'liq | 👔 Kiyim | 📱 Aloqa\n"
        "📚 Ta'lim | 🎬 Ko'ngil ochar | 📦 Boshqa"
    )
    await message.answer(help_text, parse_mode="Markdown")


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


@router.message(Command("hafta"))
async def cmd_week(message: types.Message):
    """Show weekly report (last 7 days)."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)
            report = ReportService(txn_repo)
            text = await report.get_week_report(user.id)
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"Week report sent to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /hafta: {e}")
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


@router.message(Command("bekor"))
async def cmd_undo(message: types.Message):
    """Undo (delete) the last transaction."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)

            last_txn = await txn_repo.get_last(user.id)
            if not last_txn:
                await message.answer("📭 Bekor qilish uchun operatsiya topilmadi.")
                return

            # Format what's being deleted
            emoji = "📈" if last_txn.type == "income" else "📉"
            type_uz = "Kirim" if last_txn.type == "income" else "Chiqim"
            cat_emoji = CATEGORY_EMOJI.get(last_txn.category, "📦")
            amount_str = format_amount(float(last_txn.amount), last_txn.currency)
            date_str = last_txn.created_at.strftime("%d.%m.%Y %H:%M") if last_txn.created_at else ""

            await txn_repo.delete(last_txn.id)

            response = (
                f"↩️ Oxirgi operatsiya bekor qilindi!\n\n"
                f"{emoji} *Tur:* {type_uz}\n"
                f"💵 *Summa:* {amount_str}\n"
                f"{cat_emoji} *Kategoriya:* {last_txn.category}\n"
                f"📅 *Sana:* {date_str}"
            )
            await message.answer(response, parse_mode="Markdown")
            logger.info(f"Transaction {last_txn.id} undone by user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error in /bekor: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")


@router.message(Command("export"))
async def cmd_export(message: types.Message):
    """Export this month's transactions as a CSV file."""
    try:
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(telegram_id=message.from_user.id)
            txn_repo = TransactionRepository(session)

            transactions = await txn_repo.get_this_month(user.id)

            if not transactions:
                await message.answer("📭 Bu oyda eksport qilish uchun operatsiya yo'q.")
                return

            # Build CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Sana", "Tur", "Summa", "Valyuta", "Kategoriya", "Tavsif"])

            for txn in transactions:
                date_str = txn.created_at.strftime("%Y-%m-%d %H:%M") if txn.created_at else ""
                type_uz = "Kirim" if txn.type == "income" else "Chiqim"
                writer.writerow([
                    date_str,
                    type_uz,
                    float(txn.amount),
                    txn.currency,
                    txn.category,
                    txn.description or "",
                ])

            csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
            doc = BufferedInputFile(csv_bytes, filename="xisobchi_export.csv")

            await message.answer_document(
                doc,
                caption=f"📤 Bu oydagi {len(transactions)} ta operatsiya eksport qilindi."
            )
            logger.info(f"CSV export sent to user {message.from_user.id} ({len(transactions)} rows)")

    except Exception as e:
        logger.error(f"Error in /export: {e}")
        await message.answer("Tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
