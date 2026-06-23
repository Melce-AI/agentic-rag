from fastapi import APIRouter

from src.auth.issuer import create_access_token
from src.auth.service import authenticate
from src.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    claims = await authenticate(payload.email, payload.password)
    token = create_access_token(claims)
    return TokenResponse(access_token=token)
