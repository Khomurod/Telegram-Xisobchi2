    from sqlalchemy.ext.asyncio import AsyncSession


    class BaseRepository:
        """Base repository providing common database session access."""

        def __init__(self, session: AsyncSession):
            self.session = session
