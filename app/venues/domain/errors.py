from app.shared.domain.errors import DomainError


class ListClosed(DomainError):
    pass


class ListPaused(DomainError):
    pass
