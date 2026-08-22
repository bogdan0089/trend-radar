from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "trend"
    postgres_password: str = "trend"
    postgres_db: str = "trend_radar"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    secret_key: str = "dev-secret-change-me-in-production"
    access_token_expire_minutes: int = 1440
    admin_username: str = "admin"
    admin_password: str = "admin123"

    llm_provider: Literal["anthropic", "openai", "gemini", "grok", "none"] = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 30
    scoring_budget_seconds: int = 900

    amazon_category_urls: str = (
        "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics,"
        "https://www.amazon.com/Best-Sellers-Home-Kitchen/zgbs/home-garden,"
        "https://www.amazon.com/Best-Sellers-Toys-Games/zgbs/toys-and-games,"
        "https://www.amazon.com/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods,"
        "https://www.amazon.com/Best-Sellers-Beauty/zgbs/beauty"
    )
    scrape_max_products: int = 8
    scrape_interval_hours: int = 6
    playwright_headless: bool = True
    scrape_proxy: str = ""
    scrape_snapshot_fallback: bool = True

    cors_origins: str = "http://localhost:3011,http://localhost:5173"

    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def category_urls(self) -> list[str]:
        """Parse AMAZON_CATEGORY_URLS, a comma separated list."""
        return [url.strip() for url in self.amazon_category_urls.split(",") if url.strip()]

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def llm_enabled(self) -> bool:
        """Without a key the deterministic fallback is always used."""
        return self.llm_provider != "none" and bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
