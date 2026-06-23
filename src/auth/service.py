import hashlib
import hmac
import secrets

from src.auth.claims import AuthClaims
from src.core.config import get_settings
from src.core.exceptions import AuthError

_ITERATIONS = 480_000


def hash_password(password: str) -> str:
    """Üret: 'salt:hash' (kullanıcı oluştururken bir kere çalışır)."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS
    )
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Doğrula: gelen şifre, saklanan 'salt:hash' ile eşleşiyor mu."""
    # Fail closed: a missing/malformed hash means auth fails (401), never a 500.
    if not stored or ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS
    )
    return hmac.compare_digest(dk.hex(), expected)


async def authenticate(email: str, password: str) -> AuthClaims:
    """Config'deki kullanıcıyla karşılaştır; doğruysa AuthClaims döndür."""
    settings = get_settings()
    if not (
        hmac.compare_digest(email, settings.auth_user_email)
        and verify_password(password, settings.auth_user_password_hash)
    ):
        raise AuthError("Invalid email or password")
    return AuthClaims(user_id=email, email=email, roles=settings.auth_user_roles)
