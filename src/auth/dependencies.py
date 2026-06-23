from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.claims import AuthClaims
from src.auth.validator import decode_token
from src.core.exceptions import AuthError

bearer_scheme = HTTPBearer(auto_error=False)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthClaims:
    if creds is None:
        raise AuthError("Missing bearer token")
    return decode_token(creds.credentials)
