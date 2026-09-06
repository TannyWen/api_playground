import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import decode_access_token

bearer_scheme = HTTPBearer()


def require_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        username = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise unauthorized
    except jwt.InvalidTokenError:
        raise unauthorized

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise unauthorized
    return user
