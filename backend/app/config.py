from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.passwords import check_strength


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", str_min_length=1)

    # Secrets have no defaults: they must come from the environment / .env.
    database_url: str
    # A short secret can be brute-forced offline from any token, letting someone forge a coordinator login.
    jwt_secret: str = Field(min_length=32)
    # The one coordinator (admin) account. There is no coordinator sign-up.
    admin_name: str
    admin_email: str
    admin_id_number: str
    # Same rules as sign-up: login guessing is only rate-limited, so a weak coordinator password is the easiest way in.
    admin_password: str
    # Password for the dev accounts made by app.seed. Only the seed script needs it.
    seed_password: str | None = None
    # Rate-limit counters (app.rate_limit). Not a secret: Redis has no host port.
    redis_url: str = "redis://redis:6379/0"
    # Virus scanner for uploads (app.virus_scan). Not a secret: clamd has no host port.
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    jwt_expire_minutes: int = 60 * 24
    upload_dir: str = "uploads"
    max_upload_mb: int = 20

    @field_validator("admin_password")
    @classmethod
    def strong_admin_password(cls, v: str) -> str:
        return check_strength(v)


settings = Settings()
