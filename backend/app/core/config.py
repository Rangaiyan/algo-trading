from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Rinz Algo"
    environment: str = "local"  # local | staging | production

    database_url: str = "postgresql+psycopg://rinz:rinz@localhost:5432/rinz"
    redis_url: str = "redis://localhost:6379/0"

    # Safety: live trading is OFF until stage gates pass (doc section 2).
    live_trading_enabled: bool = False

    # Telegram (doc section 14). Chat IDs are an allow-list, comma separated.
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""

    # MT5 gateway (Windows service)
    mt5_gateway_url: str = ""
    mt5_gateway_token: str = ""

    @property
    def telegram_chat_id_list(self) -> list[str]:
        return [c.strip() for c in self.telegram_chat_ids.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
