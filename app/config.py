from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_api_key: str
    groq_api_key: str
    database_url: str
    database_url_sync: str = ""
    app_name: str = "City Health Clinic Scheduling"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
