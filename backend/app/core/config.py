from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "MedAssist AI"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    APP_NAME: str = "Medication Assistant API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Local inference. No API key, no vendor account, no per-token cost: Ollama serves
    # on loopback and the weights sit on this machine. That is a data-protection
    # decision before it is a cost one — the inputs this project would send a model are
    # a named patient's medication list, adherence history and free-text symptom
    # reports, which is precisely the category of data that should not leave the host.
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

settings = Settings()
