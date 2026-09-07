import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

# Teaching note: in a real deployment, SECRET_KEY belongs in a secrets
# manager, never in source control. This is a disposable training API with
# no real user data behind it, so the fixed fallback below trades that
# guarantee for being self-contained: no App Setting required, and a restart
# never invalidates a token or credential card already handed out. Anyone
# with read access to this repo could mint their own valid token as a result
# -- fine here since /v1 is entirely read-only over fake seeded data, but set
# JWT_SECRET_KEY explicitly (it always takes precedence) before reusing this
# pattern anywhere real data or write access is involved.
_FIXED_DEV_SECRET = "3268dcae51775797d3daca03f2ab1c9b47aa820810582d5d42215cc3103915fa"
SECRET_KEY = os.getenv("JWT_SECRET_KEY", _FIXED_DEV_SECRET)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return secrets.compare_digest(candidate, password_hash)


def create_access_token(subject: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expires_at}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]
