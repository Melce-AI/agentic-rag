"""Test helpers for bypassing JWT auth in endpoint tests.

Instead of minting real RS256 tokens in every test, override the ``current_user``
dependency with a fixed fake user so protected endpoints accept requests. Call
``override_auth(app)`` in a fixture.
"""

from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user


def fake_user() -> AuthClaims:
    """A stand-in authenticated user for tests."""
    return AuthClaims(user_id="test-user", email="test@example.com", roles=["admin"])


def override_auth(app) -> None:
    """Make every protected endpoint accept requests without a real token."""
    app.dependency_overrides[current_user] = fake_user
