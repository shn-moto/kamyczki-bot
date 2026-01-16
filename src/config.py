from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str

    postgres_user: str = "kamyczki"
    postgres_password: str = "kamyczki_secret"
    postgres_db: str = "kamyczki_bot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Web server for Mini App
    web_port: int = 8080
    webapp_base_url: str = ""  # HTTPS URL from ngrok/cloudflared

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
