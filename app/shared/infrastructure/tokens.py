import secrets

from app.shared.application.ports import TokenGenerator


class SecretsTokenGenerator(TokenGenerator):
    def new_token(self) -> str:
        return secrets.token_urlsafe(24)  # 192 bits de entropía
