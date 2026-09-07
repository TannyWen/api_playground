"""Connection endpoints: reach it, then authenticate against it.

Two routes rather than one, on purpose. "I can't connect" has two independent
causes, and the workshop's first lesson is to bisect them:

    GET /v1/ping    -- no auth. Proves network, DNS, TLS, proxy, cold start.
    GET /v1/whoami  -- auth.    Proves the token.
"""
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models
from app.auth import bearer_scheme
from app.database import get_db
from app.security import ALGORITHM, SECRET_KEY, create_access_token, verify_password
from app.v1 import config, ratelimit, schemas
from app.v1.deps import current_user, principal
from app.v1.errors import ApiError
from app.version import STARTED_AT, __version__, git_commit

router = APIRouter(tags=["v1: connection"])


@router.get("/ping", response_model=schemas.PingOut)
def ping():
    """Liveness check. No authentication -- deliberately the simplest thing here.

    Also the answer to "is the new version actually live": app_version is
    bumped by hand, git_commit comes straight from .git if the deploy included
    it, and uptime_seconds resets on every real restart -- so a stale process
    is visible even if someone forgot to bump the version string.
    """
    now = datetime.now(timezone.utc)
    return schemas.PingOut(
        server_time=now,
        next_step=(
            "POST /v1/auth/token with Body -> x-www-form-urlencoded "
            "(fields: username, password), then GET /v1/whoami"
        ),
        app_version=__version__,
        git_commit=git_commit(),
        process_started_at=STARTED_AT,
        uptime_seconds=int((now - STARTED_AT).total_seconds()),
    )


@router.post("/auth/token", response_model=schemas.TokenOut)
def issue_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Exchange credentials for a bearer token.

    Form-encoded, not JSON. That is not an oversight -- it mirrors the OAuth2
    password grant, and working out *why* a JSON body fails here is one of the
    workshop's most useful ten minutes. Failures arrive in the /v1 error
    envelope.
    """
    user = (
        db.query(models.User)
        .filter(models.User.username == form_data.username)
        .first()
    )
    if not user or not verify_password(
        form_data.password, user.password_hash, user.password_salt
    ):
        raise ApiError(
            401,
            "Incorrect username or password.",
            code="unauthenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_at = create_access_token(subject=user.username)
    return schemas.TokenOut(access_token=token, expires_at=expires_at)


@router.get("/whoami", response_model=schemas.WhoAmIOut)
def whoami(
    user: models.User = Depends(current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    who: str = Depends(principal),
):
    """Who am I, and when does my token die?

    The expiry countdown turns the mid-session "everything suddenly returns 401"
    mystery into a two-second self-diagnosis. This is also the only route that
    actually uses the User that require_token returns -- every other route
    discards it.
    """
    expires_at = expires_in = None
    try:
        payload = jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM]
        )
        if payload.get("exp"):
            expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            expires_in = max(
                0, int((expires_at - datetime.now(timezone.utc)).total_seconds())
            )
    except jwt.InvalidTokenError:
        # Unreachable in practice -- current_user already validated the token.
        pass

    _, remaining, reset_in = ratelimit.peek(
        f"global:{who}", config.RATE_LIMIT_RPM, 60
    )

    return schemas.WhoAmIOut(
        username=user.username,
        user_id=user.id,
        token_expires_at=expires_at,
        token_expires_in_seconds=expires_in,
        server_time=datetime.now(timezone.utc),
        rate_limit=schemas.RateLimitOut(
            limit=config.RATE_LIMIT_RPM,
            remaining=remaining,
            resets_in_seconds=reset_in,
        ),
    )
