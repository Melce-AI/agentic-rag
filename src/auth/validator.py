import jwt

from src.auth.claims import AuthClaims
from src.auth.keys import load_public_key
from src.core.config import get_settings
from src.core.exceptions import AuthError


def decode_token(token: str) -> AuthClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            load_public_key(),
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")

    return AuthClaims(
        user_id=payload["sub"],
        email=payload["email"],
        roles=payload.get("roles", []),
    )
