from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "MedAssist AI"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    APP_NAME: str = "Medication Assistant API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str
    ALLOWED_ORIGINS: str = "*"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Gemini API configuration for cloud inference
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-latest"
    GEMINI_ENABLED: bool = True
    GEMINI_TIMEOUT: float = 30.0

    # Legacy Ollama fields (retained for backward compatibility or switching back)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # SQL statement logging. Gated on its own flag so DEBUG can stay True without
    # flooding the log with every query — a plausible route to logging patient data
    # in any shared environment.
    SQL_ECHO: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_gemini(self) -> "Settings":
        if self.GEMINI_ENABLED and not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY must be set if GEMINI_ENABLED is True")
        return self

settings = Settings()
