import hashlib


def hash_token(token: str) -> str:
    """SHA-256 en hexadecimal. Solo se guarda el hash: la base nunca contiene un token utilizable."""
    return hashlib.sha256(token.encode()).hexdigest()
