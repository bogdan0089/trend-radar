from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def login(self, username: str, password: str) -> TokenResponse:
        user = self.users.get_by_username(username)

        # Однакова помилка для «нема юзера» і «невірний пароль» —
        # інакше форма логіну підказує, які логіни існують.
        if user is None or not verify_password(password, user.password_hash):
            logger.warning("Невдалий вхід для username=%s", username)
            raise InvalidCredentialsError("Невірний логін або пароль")

        if not user.is_active:
            logger.warning("Спроба входу заблокованим користувачем username=%s", username)
            raise InvalidCredentialsError("Обліковий запис вимкнено")

        logger.info("Успішний вхід username=%s", username)
        return TokenResponse(access_token=create_access_token(user.username))

    def get_by_username(self, username: str) -> User | None:
        return self.users.get_by_username(username)

    def ensure_admin(self, username: str, password: str) -> bool:
        """Ідемпотентно створює адміна на старті. True — якщо реально створив."""
        if self.users.get_by_username(username) is not None:
            logger.info("Адмін '%s' уже існує — пропускаю", username)
            return False

        self.users.create(username=username, password_hash=hash_password(password))
        self.db.commit()
        logger.info("Створено адміна '%s'", username)
        return True
