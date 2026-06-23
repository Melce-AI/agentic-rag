from pydantic import BaseModel, Field


class AuthClaims(BaseModel):
    """Decoded JWT payload — who the authenticated user is."""

    user_id: str  # JWT "sub" claim
    email: str
    roles: list[str] = Field(default_factory=list)
