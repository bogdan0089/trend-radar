"""FastAPI dependency turning a bearer token into a User."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsError
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token into a user, or reject the request with 401.

    Every failure raises the same error on purpose: telling a caller whether the
    token was missing, expired or belonged to a deleted user only helps them.
    """
    if credentials is None:
        raise InvalidCredentialsError("no bearer token")

    username = decode_access_token(credentials.credentials)
    if username is None:
        logger.warning("Rejected a malformed or expired token")
        raise InvalidCredentialsError("malformed or expired token")

    user = UserRepository(db).get_by_username(username)
    if user is None or not user.is_active:
        logger.warning("Token is valid but user '%s' is missing or disabled", username)
        raise InvalidCredentialsError("user missing or disabled")

    return user
