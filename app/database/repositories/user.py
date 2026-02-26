from sqlalchemy import select, func
from app.database.models import User
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Repository for User CRUD operations."""

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(self, telegram_id: int, first_name: str = None, username: str = None) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_or_create(self, telegram_id: int, first_name: str = None, username: str = None) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            user = await self.create(telegram_id, first_name, username)
        else:
            changed = False
            # Only use Telegram profile name as a fallback when no name has been stored yet.
            # Once the user types their own name during onboarding, never overwrite it.
            if first_name and user.first_name is None:
                user.first_name = first_name
                changed = True
            if username != user.username:  # username can become None (user removed it)
                user.username = username
                changed = True
            if changed:
                await self.session.commit()
                await self.session.refresh(user)
        return user

    async def update_phone(self, telegram_id: int, phone_number: str) -> None:
        """Save phone number collected during onboarding."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.phone_number = phone_number
            await self.session.commit()

    async def update_name(self, telegram_id: int, first_name: str) -> None:
        """Update the user's display name (from onboarding input)."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.first_name = first_name
            await self.session.commit()

    async def update_city(self, telegram_id: int, city: str) -> None:
        """Save user's city preference (for Ramadan fasting times)."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.city = city
            await self.session.commit()

    async def get_total_count(self) -> int:
        """Return total number of registered users."""
        result = await self.session.execute(select(func.count(User.id)))
        return result.scalar() or 0

    async def delete_by_telegram_id(self, telegram_id: int) -> bool:
        """Hard-delete a user and all their transactions (cascade).
        Returns True if the user existed and was deleted, False if not found.
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False
        await self.session.delete(user)
        await self.session.commit()
        return True
