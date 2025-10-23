from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.repositories.user import UserRepository

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from app.models.user import User


class UserService:
    """Business logic for working with :class:`~app.models.user.User`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    async def register(self, email: str, password: str) -> User:
        existing = await self._repo.get_by_email(email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        hashed_password = get_password_hash(password)
        user = await self._repo.create(email=email, hashed_password=hashed_password)
        await self._session.commit()
        return user

    async def get_by_id(self, user_id: int) -> User:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def delete(self, user_id: int) -> None:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        await self._repo.delete(user)
        await self._session.commit()
