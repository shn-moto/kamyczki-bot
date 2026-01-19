from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str

    # Database - supports both local PostgreSQL and Neon serverless
    # For Neon: set DATABASE_URL directly (connection string with pooler)
    database_url: str = ""  # Direct connection string (takes priority)
    postgres_user: str = "kamyczki"
    postgres_password: str = "kamyczki_secret"
    postgres_db: str = "kamyczki_bot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Web server for Mini App
    web_port: int = 8080
    webapp_base_url: str = ""  # HTTPS URL for Mini App

    # Serverless ML (Modal.com)
    modal_endpoint_url: str = ""  # Modal web endpoint URL
    use_local_ml: bool = True  # False = use Modal, True = use local CLIP

    # Webhook mode (for Cloud Run)
    use_webhook: bool = False  # False = polling, True = webhook
    webhook_url: str = ""  # Cloud Run URL for webhook
    webhook_secret: str = ""  # Secret token for webhook validation

    @property
    def db_url(self) -> str:
        """Get database URL - prefers direct URL over constructed one."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
