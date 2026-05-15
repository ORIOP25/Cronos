class DomainError(Exception):
    """Exceção de domínio — o endpoint mapeia para HTTP status code."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(DomainError):
    def __init__(self, message: str = "Recurso não encontrado"):
        super().__init__(message, status_code=404)


class ConflictError(DomainError):
    def __init__(self, message: str = "Conflito"):
        super().__init__(message, status_code=409)


class ForbiddenError(DomainError):
    def __init__(self, message: str = "Acesso proibido"):
        super().__init__(message, status_code=403)
