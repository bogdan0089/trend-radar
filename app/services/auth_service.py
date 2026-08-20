from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def login(self, username: str, password: str) -> str:
        """Authenticate and return a signed access token."""
        user = self.users.get_by_username(username)

        if user is None or not verify_password(password, user.password_hash):
            logger.warning("Failed login for username=%s", username)
            raise InvalidCredentialsError()

        if not user.is_active:
            logger.warning("Login attempt by a disabled user username=%s", username)
            raise InvalidCredentialsError("account disabled")

        logger.info("Successful login username=%s", username)
        return create_access_token(user.username)

    def get_by_username(self, username: str) -> User | None:
        return self.users.get_by_username(username)

    def ensure_admin(self, username: str, password: str) -> bool:
        """Create the admin user if missing. Returns True when it was created."""
        if self.users.get_by_username(username) is not None:
            logger.info("Admin '%s' already exists, skipping", username)
            return False

        self.users.create(username=username, password_hash=hash_password(password))
        self.db.commit()
        logger.info("Created admin '%s'", username)
        return True
