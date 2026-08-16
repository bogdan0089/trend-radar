from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def load_fixture():
    """Читає HTML-фікстуру за іменем файлу."""

    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(scope="session")
def bestsellers_html(load_fixture) -> str:
    return load_fixture("amazon_bestsellers.html")


@pytest.fixture(scope="session")
def blocked_html(load_fixture) -> str:
    return load_fixture("amazon_blocked.html")
