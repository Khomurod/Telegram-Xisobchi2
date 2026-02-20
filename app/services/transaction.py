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
        """
        # Ensure user exists
        user = await self.user_repo.get_or_create(telegram_id, first_name, username)

        # Parse text
        parsed = parse_transaction(text)
        if not parsed:
            logger.warning(f"Parse failed for user {telegram_id}: '{text}'")
            return {"success": False, "error": "parse_failed"}

        # Store transaction
        txn = await self.txn_repo.create(
            user_id=user.id,
            type=parsed.type,
            amount=parsed.amount,
            currency=parsed.currency,
            category=parsed.category,
            description=parsed.description,
        )

        logger.info(f"Transaction #{txn.id} saved: {parsed.type} {parsed.amount} {parsed.currency} [{parsed.category}] for user {telegram_id}")

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
