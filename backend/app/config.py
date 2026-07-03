from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+asyncpg://scheduler:scheduler@localhost:5432/job_scheduler"
    database_url_sync: str = "postgresql://scheduler:scheduler@localhost:5432/job_scheduler"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    worker_concurrency: int = 4
    worker_poll_interval: float = 1.0
    worker_heartbeat_interval: float = 10.0
    job_claim_timeout_seconds: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
