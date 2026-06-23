from fastapi import APIRouter, Request

from src.auth.issuer import create_access_token
from src.auth.service import authenticate
from src.schemas.auth import LoginRequest, TokenResponse
from src.schemas.response import SuccessResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=SuccessResponse[TokenResponse])
async def login(payload: LoginRequest, request: Request) -> SuccessResponse[TokenResponse]:
    claims = await authenticate(payload.email, payload.password)
    token = create_access_token(claims)
    return SuccessResponse(
        data=TokenResponse(access_token=token), request_id=request.state.request_id
    )
