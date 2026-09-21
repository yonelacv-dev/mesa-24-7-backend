from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int
    venue_id: int
    username: str


@dataclass(frozen=True)
class LoginResult:
    token: str  # solo se devuelve aquí, una vez; en la base queda su hash
    user: AuthenticatedUser
