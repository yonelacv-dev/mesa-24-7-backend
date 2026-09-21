from app.shared.domain.errors import DomainError


class InvalidTransition(DomainError):
    pass


class ActorNotAllowed(DomainError):
    pass
