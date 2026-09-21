from app.shared.application.errors import Unauthorized


class InvalidCredentials(Unauthorized):
    def __init__(self) -> None:
        super().__init__("invalid_credentials", "Usuario o contraseña incorrectos.")


class InvalidToken(Unauthorized):
    def __init__(self) -> None:
        super().__init__("invalid_token", "Tu sesión no es válida. Inicia sesión de nuevo.")
