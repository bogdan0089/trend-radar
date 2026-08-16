from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL
    postgres_user: str = "trend"
    postgres_password: str = "trend"
    postgres_db: str = "trend_radar"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # Auth
    secret_key: str = "dev-secret-change-me-in-production"
    access_token_expire_minutes: int = 1440
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # LLM
    llm_provider: Literal["anthropic", "openai", "none"] = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 30

    # Скрапінг
    amazon_category_url: str = "https://www.amazon.com/Best-Sellers/zgbs"
    scrape_max_products: int = 20
    scrape_interval_hours: int = 6
    playwright_headless: bool = True
    scrape_proxy: str = ""
    # Amazon блокує частину IP. Коли живий збір не пройшов — беремо демо-снапшот
    # із app/seed_data/, щоб панель не була порожньою. Запуск позначається
    # як 'partial', а не 'success': блокування має лишатись видимим.
    scrape_snapshot_fallback: bool = True

    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def llm_enabled(self) -> bool:
        """Без ключа завжди працюємо на детермінованому fallback."""
        return self.llm_provider != "none" and bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
