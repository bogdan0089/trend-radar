"""FastAPI dependency turning a bearer token into a User."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ForbiddenError, InvalidCredentialsError
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


def is_admin(user: User) -> bool:
    """The account created from ADMIN_USERNAME; everyone else registered themselves."""
    return user.username == settings.admin_username


def get_admin(user: User = Depends(get_current_user)) -> User:
    """Shared data such as the sales history is changed by the admin only."""
    if not is_admin(user):
        raise ForbiddenError("Only the admin can change the sales history")
    return user
