import pytest

from app.core.config import DEV_ADMIN_PASSWORD, DEV_SECRET_KEY, Settings

# _env_file=None: these assert on the declared defaults, so a developer's own
# .env must not decide whether they pass.


def test_production_refuses_the_published_secret_key() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            admin_password="chosen-by-the-operator",
        )


def test_production_refuses_the_published_admin_password() -> None:
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="chosen-by-the-operator",
        )


def test_production_accepts_its_own_secrets() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="chosen-by-the-operator",
        admin_password="also-chosen",
    )

    assert settings.secret_key == "chosen-by-the-operator"


def test_local_keeps_the_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.secret_key == DEV_SECRET_KEY
    assert settings.admin_password == DEV_ADMIN_PASSWORD
