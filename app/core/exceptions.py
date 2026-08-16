"""Доменні винятки.

Сервіси кидають їх, шар API мапить у HTTP. Сервіс не знає про HTTP-статуси.
"""


class DomainError(Exception):
    """База для всіх помилок бізнес-логіки."""


class NotFoundError(DomainError):
    """Сутності не існує."""


class AlreadyExistsError(DomainError):
    """Порушення унікальності на рівні бізнес-правил."""


class InvalidCredentialsError(DomainError):
    """Невірний логін або пароль."""


class ValidationError(DomainError):
    """Дані не проходять бізнес-перевірку (напр. битий CSV)."""


class ScrapingError(DomainError):
    """Скрапер не зміг зібрати дані: капча, блок, таймаут, зміна верстки."""


class ExternalServiceError(DomainError):
    """Зовнішній сервіс (LLM, Google Trends) недоступний або відповів сміттям."""
