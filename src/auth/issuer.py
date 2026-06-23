from datetime import datetime, timedelta, timezone

import jwt

from src.auth.claims import AuthClaims
from src.auth.keys import load_private_key
from src.core.config import get_settings


def create_access_token(claims: AuthClaims) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": claims.user_id,        # standart JWT claim: "subject" = kullanıcı
        "email": claims.email,
        "roles": claims.roles,
        "iat": now,                   # issued at (ne zaman üretildi)
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "iss": settings.jwt_issuer,   # kim üretti (validator bunu kontrol edecek)
    }
    return jwt.encode(payload, load_private_key(), algorithm="RS256")
