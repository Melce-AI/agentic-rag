# JWT Authentication — Design & Walkthrough

This document explains the JWT authentication layer added to Agentic RAG: **what**
we built, **where** each piece lives, **how** it works, **why** we made each
choice, and **how to test it**. It is written to be read top-to-bottom — by the
end you should understand the whole system the way it was built, step by step.

> Status: **Phase 1 complete** (login + token validation + endpoint protection).
> Phases 2–3 (refresh tokens, user registration, role-based authz) are planned —
> see [Roadmap](#roadmap).

---

## 1. The big picture: two roles

Authentication has two separate responsibilities. It helps to keep them distinct:

- **Auth server (Identity Provider)** — verifies credentials and **issues** signed
  tokens. This is our `/auth/login` endpoint.
- **Resource server** — **validates** an incoming token and reads its claims to
  decide whether to serve a protected request. This is our `current_user`
  dependency, applied to the agent/search/documents routers.

In a large system these are separate services. In Phase 1 both live inside the
same FastAPI app — which is normal and correct for this scale.

This follows the standard shape of a *resource server* that only validates
tokens. We wrote our own equivalent **including the issuing half** (the
`/auth/login` token minting) that a pure validator does not provide.

---

## 2. End-to-end flow

```
1. POST /auth/login  { email, password }
        │  credentials valid?
        ▼
   issuer.create_access_token()  ──►  signs payload with the PRIVATE key (RS256)
        │
        ▼  returns { access_token, token_type: "bearer" }

2. POST /agent/ask   Authorization: Bearer <access_token>
        │
        ▼
   Depends(current_user)
        │   └─ validator.decode_token()  ──►  verifies signature with the PUBLIC key
        │         ├─ bad signature / expired / wrong issuer ──► AuthError → 401
        │         └─ valid ──► AuthClaims(user_id, email, roles)
        ▼
   endpoint runs, with `user` available (for HITL / logging / authz)
```

The crucial idea of **RS256**: the **private key signs**, the **public key
verifies**. They are different keys. The login endpoint is the only place that
touches the private key; everything that validates a token uses the public key.

---

## 3. Why RS256 (and not HS256)?

| | HS256 (symmetric) | RS256 (asymmetric) — **our choice** |
|---|---|---|
| Keys | one shared secret signs *and* verifies | private signs, public verifies |
| Sharing | every verifier needs the secret (can also forge) | verifiers only need the public key (cannot forge) |
| Fit | simplest, single-service | matches a real IdP/resource-server split; safe to distribute the public key |

RS256 mirrors how a resource server consumes tokens from an external IdP: it
only ever needs the public key, so it can validate without being able to mint
tokens. Even though both halves live in one app today, building on RS256 keeps
the door open to splitting them later with zero token-format change.

---

## 4. Files — what, where, why

All auth logic lives in `src/auth/`, organized by responsibility. Layering
follows the project rule: `api → auth → core`.

| File | Responsibility | Why it exists |
|---|---|---|
| [`src/auth/claims.py`](../../src/auth/claims.py) | `AuthClaims` Pydantic model — the decoded token payload (`user_id`, `email`, `roles`) | A typed, validated representation of "who the user is". Pydantic (not a dataclass) because the project uses Pydantic everywhere and we are parsing external data. |
| [`src/auth/keys.py`](../../src/auth/keys.py) | `load_private_key()`, `load_public_key()` — read the PEM files | Single source for key loading; `@lru_cache` so a key is read from disk once. Paths come from config, never hardcoded. |
| [`src/auth/issuer.py`](../../src/auth/issuer.py) | `create_access_token(claims) -> str` — sign a token with the private key | The "issuing half". Builds the payload (`sub`, `email`, `roles`, `iat`, `exp`, `iss`) and signs it. |
| [`src/auth/validator.py`](../../src/auth/validator.py) | `decode_token(token) -> AuthClaims` — verify with the public key | The "validating half". Raises `AuthError` on bad/expired/wrong-issuer tokens. |
| [`src/auth/dependencies.py`](../../src/auth/dependencies.py) | `current_user` — FastAPI dependency (HTTPBearer) | The HTTP bridge. Extracts the bearer token and calls `decode_token`. Adds the "Authorize" button in Swagger. |
| [`src/auth/service.py`](../../src/auth/service.py) | `authenticate()`, `hash_password()`, `verify_password()` | Login logic, kept out of the router. Verifies the password against the configured user. |
| [`src/auth/testing.py`](../../src/auth/testing.py) | `fake_user()`, `override_auth(app)` | Lets tests bypass auth without minting real tokens. |
| [`src/schemas/auth.py`](../../src/schemas/auth.py) | `LoginRequest`, `TokenResponse` | DTOs live in `schemas/` (project convention), not in the router. |
| [`src/api/routers/auth.py`](../../src/api/routers/auth.py) | `POST /auth/login` | Thin router: `authenticate` → `create_access_token` → `TokenResponse`. |

Supporting changes:

- **Config** — [`src/core/config.py`](../../src/core/config.py): `jwt_private_key_path`,
  `jwt_public_key_path`, `jwt_issuer`, `jwt_access_token_expire_minutes`,
  `auth_user_email`, `auth_user_password_hash`, `auth_user_roles`.
- **Exceptions** — [`src/core/exceptions.py`](../../src/core/exceptions.py): `AuthError`
  (extends `AppException`, status 401) so auth failures return the project's
  standard JSON error shape via the existing handlers.
- **`.gitignore`**: `keys/` and `*.pem` — signing keys must never be committed.
- **`.env.example`**: documents all new settings + the keygen commands.
- **`src/app.py`**: registers the auth router and loads the keys at startup
  (see [Fail-fast](#7-fail-fast)).

---

## 5. The RSA keypair

Tokens are signed/verified with an RSA keypair. Generate it once. The keys are
gitignored — every environment (and CI) generates its own.

```bash
mkdir -p keys
openssl genrsa -out keys/jwt_private.pem 2048
openssl rsa -in keys/jwt_private.pem -pubout -out keys/jwt_public.pem
```

- `jwt_private.pem` — signs tokens (kept secret, mode `600`). Only the login
  endpoint reads it.
- `jwt_public.pem` — verifies tokens. Safe to distribute.

> **Never commit these files.** A leaked private key lets anyone mint valid
> tokens. `keys/` and `*.pem` are in `.gitignore`.

---

## 6. The Phase-1 user store

We deliberately have **no users table yet**. The project's Postgres connects with
a **read-only role** (`sentinel_ro`) by design (defense-in-depth) — it physically
cannot write users. Adding a write path is a conscious decision left for a later
phase (see [Roadmap](#roadmap)).

For Phase 1 there is **one bootstrap user in config**, and its password is stored
as a **pbkdf2 hash**, never plaintext:

```
AUTH_USER_PASSWORD_HASH = "salt:pbkdf2_sha256_hex"
```

Generate a hash for a new password with:

```bash
uv run --no-sync python -c "from src.auth.service import hash_password; print(hash_password('your-password'))"
```

---

## 7. Fail-fast

**Principle:** surface configuration errors at **startup**, not on the first
request. A misconfigured deployment should crash immediately with a clear error
rather than serve traffic and 500 later.

The app already fails fast on Qdrant, MCP, and Redis (they initialize in the
`lifespan`). We extended this to auth: the JWT keys are loaded in `lifespan` too,
so a missing or malformed key crashes the app at startup:

```python
# src/app.py lifespan
load_private_key()
load_public_key()
logger.info("JWT signing keys loaded.")
```

Note: the existing endpoint tests build `TestClient(app)` **without** the
`with` context manager, so they do not trigger `lifespan` — they are unaffected
by this. Real startup (uvicorn / Docker) and any `with TestClient(app)` test do
trigger it, so those environments must have the keys present.

---

## 8. Endpoint protection

Two ways to apply `current_user`, used intentionally:

- **Method A — per endpoint** (when the handler needs to know *who*):
  added to [`agent.py`](../../src/api/routers/agent.py) so the agent has the user
  for HITL / logging / authz later.
  ```python
  async def agent_ask(payload: AgentAskRequest, request: Request,
                      user: AuthClaims = Depends(current_user)):
  ```
- **Method B — per router** (pure lock, no user object needed):
  applied to [`search.py`](../../src/api/routers/search.py) and
  [`documents.py`](../../src/api/routers/documents.py).
  ```python
  router = APIRouter(prefix="/search", tags=["Search"],
                     dependencies=[Depends(current_user)])
  ```

`/health` is intentionally left open (load balancers / monitoring).

---

## 9. Security decisions

- **Algorithm pinned** — `jwt.decode(..., algorithms=["RS256"])`. We never trust
  the token's own `alg` header, which blocks the `alg=none` / algorithm-confusion
  attacks.
- **Issuer verified** — `jwt.decode(..., issuer=settings.jwt_issuer)` rejects
  tokens not minted by us.
- **Expiry** — PyJWT checks `exp` automatically and raises `ExpiredSignatureError`.
- **Exception order** — `ExpiredSignatureError` is caught before
  `InvalidTokenError` (it is a subclass; the general one would otherwise mask it).
- **Constant-time comparison** — `hmac.compare_digest` for both email and password
  hash, so attackers cannot infer secrets from response timing.
- **No user enumeration** — wrong email and wrong password return the *same*
  message ("Invalid email or password").
- **Password hashing** — pbkdf2-HMAC-SHA256, 480k iterations, random per-password
  salt (Python stdlib — no extra dependency).

---

## 10. How we tested it

Each layer was verified in isolation before wiring the next. These commands run
without the full stack (no Qdrant/MCP/Redis needed). On this Intel-Mac dev box,
always run Python through `uv run --no-sync` (see local notes on the onnxruntime
wheel issue).

**Lint + format (always):**
```bash
uv run --no-sync ruff check src/auth/ src/api/routers/ src/schemas/auth.py
```

**Keys load:**
```bash
uv run --no-sync python -c "from src.auth.keys import load_private_key, load_public_key; \
print(load_private_key().startswith('-----BEGIN'), load_public_key().startswith('-----BEGIN'))"
```

**Issue + validate a token (round trip):**
```bash
uv run --no-sync python -c "
from src.auth.claims import AuthClaims
from src.auth.issuer import create_access_token
from src.auth.validator import decode_token
token = create_access_token(AuthClaims(user_id='u1', email='ece@qkare.com', roles=['admin']))
print(decode_token(token))            # -> AuthClaims(...)
"
```

**Login logic (valid / wrong password / wrong email):**
```bash
uv run --no-sync python -c "
import asyncio
from src.auth.service import authenticate
from src.core.exceptions import AuthError
async def main():
    print(await authenticate('ece@qkare.com', 'changeme123'))   # -> AuthClaims
    for email, pw in [('ece@qkare.com','wrong'), ('nobody@x.com','changeme123')]:
        try: await authenticate(email, pw)
        except AuthError as e: print('rejected:', e.message)
asyncio.run(main())
"
```

**Full HTTP flow with a minimal app (no infra needed):**
```bash
uv run --no-sync python -c "
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from src.api.routers.auth import router as auth_router
from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user
from src.core.exceptions import AppException

app = FastAPI(); app.include_router(auth_router)
@app.exception_handler(AppException)
async def h(r, e): return JSONResponse(status_code=e.status_code, content={'message': e.message})
@app.get('/protected')
async def p(user: AuthClaims = Depends(current_user)): return {'email': user.email}

c = TestClient(app)
tok = c.post('/auth/login', json={'email':'ece@qkare.com','password':'changeme123'}).json()['access_token']
print('no token  ->', c.get('/protected').status_code)                                  # 401
print('token     ->', c.get('/protected', headers={'Authorization': f'Bearer {tok}'}).status_code)  # 200
"
```

**Tests that hit protected endpoints** (e.g. `tests/test_rag_foundation.py`) use an
autouse fixture that calls `override_auth(app)` so they pass without real tokens:
```python
@pytest.fixture(autouse=True)
def _bypass_auth():
    override_auth(app)
    yield
    app.dependency_overrides.clear()
```

**Full suite (needs the package set installed — use Docker on the Intel Mac):**
```bash
uv run pytest
```

---

## 11. Running it for real

Local `uv run uvicorn` cannot start the full app on the Intel Mac (the
`langgraph-checkpoint-redis` / onnxruntime wheels are unavailable). Use Docker,
which brings up Qdrant + Postgres + Redis + MCP:

1. Generate the keypair (Section 5) — keys are not in the image, mount/inject them.
2. Set `AUTH_USER_PASSWORD_HASH` (Section 6) in `.env`.
3. Start the stack, open Swagger at `/docs`.
4. `POST /auth/login` → copy the `access_token`.
5. Click **Authorize** (top-right), paste the token → all protected endpoints work.

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| **1** | RS256 keypair, `/auth/login`, `current_user`, endpoint protection, fail-fast, tests | ✅ Done |
| **2** | Refresh tokens + rotation + reuse-detection + revocation (needs a store) | ⬜ Planned |
| **3** | Register endpoint + users table + role-based authz (`require_role`) | ⬜ Planned |

Phase 3 requires a **write-capable** path for users without weakening the
read-only `sentinel_ro` role — likely a separate `auth_rw` role or a dedicated
auth database. That decision is open.
