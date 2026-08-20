from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthRepository:
    """Checks that the database connection is alive."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ping(self) -> None:
        self.db.execute(text("SELECT 1"))
