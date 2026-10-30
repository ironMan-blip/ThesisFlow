from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://thesisflow:thesisflow@localhost:5432/thesisflow"
    jwt_secret: str = "change-me"
    # The one coordinator (admin) account. There is no coordinator sign-up.
    admin_email: str = "coordinator@thesisflow.test"
    admin_id_number: str = "000000"
    admin_password: str = "password123"
    jwt_expire_minutes: int = 60 * 24
    upload_dir: str = "uploads"
    max_upload_mb: int = 20


settings = Settings()
