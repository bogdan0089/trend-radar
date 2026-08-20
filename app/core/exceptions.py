"""Domain exceptions. Services raise them; the API layer reads http_status_code."""


class DomainError(Exception):
    def __init__(
        self,
        message: str,
        *,
        http_status_code: int,
        info: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status_code = http_status_code
        self.info: dict = info or {}


class NotFoundError(DomainError):
    def __init__(self, resource: str, identifier: str | int = "") -> None:
        msg = f"{resource} not found" + (f": {identifier}" if identifier else "")
        super().__init__(
            msg,
            http_status_code=404,
            info={"resource": resource, "id": str(identifier)},
        )


class AlreadyExistsError(DomainError):
    def __init__(self, resource: str, identifier: str = "") -> None:
        msg = f"{resource} already exists" + (f": {identifier}" if identifier else "")
        super().__init__(
            msg,
            http_status_code=409,
            info={"resource": resource, "id": identifier},
        )


class InvalidCredentialsError(DomainError):
    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "Invalid credentials",
            http_status_code=401,
            info={"reason": reason} if reason else None,
        )


class ValidationError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, http_status_code=422)


class ScrapingError(DomainError):
    """Captcha, block, timeout, or layout change from the scraper."""

    def __init__(self, message: str) -> None:
        super().__init__(message, http_status_code=502)


class ExternalServiceError(DomainError):
    """An external service (LLM, Google Trends) is down or returned garbage."""

    def __init__(self, message: str) -> None:
        super().__init__(message, http_status_code=502)
