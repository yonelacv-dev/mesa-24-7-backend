from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "waiting_list"

    cors_origins: list[str] = ["http://localhost:5173"]
    debug: bool = False
    rate_limit_enabled: bool = True
    sse_heartbeat_seconds: float = 15

    @property
    def database_url(self) -> str:
        password = f":{quote_plus(self.mysql_password)}" if self.mysql_password else ""
        return (
            f"mysql+aiomysql://{quote_plus(self.mysql_user)}{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
