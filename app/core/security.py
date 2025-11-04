from passlib.context import CryptContext

_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")                   


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if ``plain_password`` matches ``hashed_password``."""

    return _password_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash ``password`` using a secure algorithm suitable for storage."""

    return _password_context.hash(password)
