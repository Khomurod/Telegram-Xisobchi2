from app.database.repositories.user import UserRepository
from app.database.repositories.transaction import TransactionRepository
from app.services.parser import parse_transaction, ParsedTransaction
from app.utils.logger import setup_logger

logger = setup_logger("transaction_service")


class TransactionService:
    """Business logic layer for processing and storing transactions."""

    def __init__(self, user_repo: UserRepository, txn_repo: TransactionRepository):
        self.user_repo = user_repo
        self.txn_repo = txn_repo

    async def process_text(
        self,
        telegram_id: int,
        text: str,
        first_name: str = None,
        username: str = None,
    ) -> dict:
        """
        Parse text and create transaction.
        Returns dict with 'success', 'transaction' or 'error'.

        NOTE: Prefer save_parsed() when you already have a ParsedTransaction
        (e.g. from a confirmation flow) to avoid re-parsing and potential
        discrepancies between what the user saw and what gets saved.
        """
        user = await self.user_repo.get_or_create(telegram_id, first_name, username)

        parsed = parse_transaction(text)
        if not parsed:
            logger.warning(f"Parse failed for user {telegram_id}: '{text}'")
            return {"success": False, "error": "parse_failed"}

        return await self._store(user, parsed, telegram_id)

    async def save_parsed(
        self,
        telegram_id: int,
        parsed: ParsedTransaction,
        first_name: str = None,
        username: str = None,
    ) -> dict:
        """
        Save an already-parsed transaction — no re-parsing.

        Use this in confirmation flows to guarantee the saved data matches
        exactly what was shown to the user at confirmation time.
        Returns dict with 'success', 'transaction' or 'error'.
        """
        user = await self.user_repo.get_or_create(telegram_id, first_name, username)
        return await self._store(user, parsed, telegram_id)

    async def save_parsed_batch(
        self,
        telegram_id: int,
        parsed_list: list[ParsedTransaction],
        first_name: str = None,
        username: str = None,
    ) -> dict:
        """
        Save multiple already-parsed transactions.

        Returns dict with 'success', 'transactions' list, and 'count'.
        """
        user = await self.user_repo.get_or_create(telegram_id, first_name, username)
        saved = []
        for parsed in parsed_list:
            result = await self._store(user, parsed, telegram_id)
            if result["success"]:
                saved.append(result["transaction"])

        return {
            "success": len(saved) > 0,
            "transactions": saved,
            "count": len(saved),
        }

    async def _store(self, user, parsed: ParsedTransaction, telegram_id: int) -> dict:
        """Internal helper: persist a ParsedTransaction to the database."""
        txn = await self.txn_repo.create(
            user_id=user.id,
            type=parsed.type,
            amount=parsed.amount,
            currency=parsed.currency,
            category=parsed.category,
            description=parsed.description,
        )

        logger.info(
            f"Transaction #{txn.id} saved: {parsed.type} {parsed.amount} "
            f"{parsed.currency} [{parsed.category}] for user {telegram_id}"
        )

        return {
            "success": True,
            "transaction": {
                "id": txn.id,
                "type": parsed.type,
                "amount": parsed.amount,
                "currency": parsed.currency,
                "category": parsed.category,
            },
        }
