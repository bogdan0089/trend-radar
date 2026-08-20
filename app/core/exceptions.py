"""Domain exceptions. Services raise them, the API layer maps them to HTTP."""


class DomainError(Exception): ...


class NotFoundError(DomainError): ...


class AlreadyExistsError(DomainError): ...


class InvalidCredentialsError(DomainError): ...


class ValidationError(DomainError): ...


class ScrapingError(DomainError):
    """Captcha, block, timeout, or layout change from the scraper."""


class ExternalServiceError(DomainError):
    """An external service (LLM, Google Trends) is down or returned garbage."""
