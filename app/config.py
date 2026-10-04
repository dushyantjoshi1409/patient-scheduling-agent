"""Application configuration loaded from environment variables and .env file.

All secrets (API keys, DB URL, Langfuse keys) are loaded from the .env file
via pydantic-settings. The Settings singleton is imported throughout the app.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the scheduling agent application.

    Loaded from environment variables and .env file. Required fields
    will cause startup failure if missing.
    """
    google_api_key: str = ""
    groq_api_key: str
    database_url: str
    database_url_sync: str = ""
    app_name: str = "City Health Clinic Scheduling"
    langfuse_secret_key: str = ""
    langfuse_public_key: str = ""
    langfuse_host: str = "https://us.cloud.langfuse.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
