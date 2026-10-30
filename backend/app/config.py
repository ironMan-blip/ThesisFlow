from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", str_min_length=1)

    # Secrets have no defaults: they must come from the environment / .env.
    database_url: str
    jwt_secret: str
    # The one coordinator (admin) account. There is no coordinator sign-up.
    admin_name: str
    admin_email: str
    admin_id_number: str
    admin_password: str
    # Password for the dev accounts made by app.seed. Only the seed script needs it.
    seed_password: str | None = None
    jwt_expire_minutes: int = 60 * 24
    upload_dir: str = "uploads"
    max_upload_mb: int = 20


settings = Settings()
