from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthRepository:
    """Єдине, що вміє — перевірити, що конекшн до БД живий."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ping(self) -> None:
        self.db.execute(text("SELECT 1"))
