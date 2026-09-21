import asyncio

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from app.auth.application.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    """argon2id. Corre en un hilo aparte porque es costoso a propósito y no debe bloquear el event loop."""

    def __init__(self) -> None:
        self._argon2 = Argon2()
        # Hash de mentira contra el que se verifica cuando el usuario no existe.
        self._decoy_hash = self._argon2.hash("decoy-password")

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._argon2.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(self._argon2.verify, password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    async def burn(self, password: str) -> None:
        await self.verify(self._decoy_hash, password)
