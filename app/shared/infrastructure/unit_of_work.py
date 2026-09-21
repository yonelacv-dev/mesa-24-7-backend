from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.application.ports import UnitOfWork


class SQLAlchemyUnitOfWork(UnitOfWork):
    """Una unidad por petición: los repositorios comparten la sesión y por tanto la transacción."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
