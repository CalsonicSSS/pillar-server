from functools import lru_cache
from pydantic_settings import BaseSettings

print("config and setting up...")


class Settings(BaseSettings):
    # the assigned values will be used as default values, it will be overridden by the values in .env file
    API_V1_PREFIX: str
    DEBUG: bool = False
    PROJECT_NAME: str = "Pillar"

    # Supabase settings
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # User & Authentication settings
    CLERK_PUBLISHABLE_KEY: str
    CLERK_SECRET_KEY: str
    CLERK_WEBHOOK_SECRET: str
    CLERK_DOMAIN: str = "direct-mole-16.clerk.accounts.dev"
    CLERK_JWT_AUDIENCE: str = "fastapi"

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    GOOGLE_SCOPES: str

    # claude llm api
    ANTHROPIC_API_KEY: str  # Claude API key
    CLAUDE_MODEL_HAIKU_3_5: str = "claude-3-5-haiku-20241022"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_app_config_settings():
    return Settings()


app_config_settings = get_app_config_settings()
print("config results:", app_config_settings)
