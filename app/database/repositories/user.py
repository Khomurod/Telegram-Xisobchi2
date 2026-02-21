from sqlalchemy import select
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
            # Update profile fields if they've changed since last seen
            changed = False
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if username != user.username:  # username can become None (user removed it)
                user.username = username
                changed = True
            if changed:
                await self.session.commit()
                await self.session.refresh(user)
        return user

