"""
VOXOPS AI Gateway — Application Settings
Loads configuration from environment variables via .env file.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


# Root of the project (two levels up from this file: configs/ → project root)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------
    # Application
    # -------------------------------------------------
    app_env: str = Field(default="development", description="Runtime environment")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    debug: bool = Field(default=True)

    # -------------------------------------------------
    # Database
    # -------------------------------------------------
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'data' / 'voxops.db'}",
        description="SQLAlchemy connection string",
    )

    # -------------------------------------------------
    # Vector Store (ChromaDB)
    # -------------------------------------------------
    chroma_db_path: str = Field(
        default=str(BASE_DIR / "chroma_db"),
        description="Persistent ChromaDB directory",
    )
    chroma_collection_name: str = Field(default="voxops_knowledge")

    # -------------------------------------------------
    # Speech-to-Text (Whisper)
    # -------------------------------------------------
    whisper_model_size: str = Field(
        default="small",
        description="Whisper model size: tiny | base | small | medium | large",
    )

    # -------------------------------------------------
    # Text-to-Speech (Coqui TTS)
    # -------------------------------------------------
    tts_model_name: str = Field(
        default="tts_models/en/ljspeech/tacotron2-DDC",
        description="Coqui TTS model identifier",
    )
    tts_output_path: str = Field(
        default=str(BASE_DIR / "data" / "tts_output"),
        description="Directory for generated audio files",
    )

    # -------------------------------------------------
    # Embedding Model
    # -------------------------------------------------
    embedding_model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="SentenceTransformers model for embeddings",
    )

    # -------------------------------------------------
    # LLM — Google Gemini (primary) / OpenRouter (fallback)
    # -------------------------------------------------
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model_name: str = Field(default="gemini-2.0-flash", description="Gemini model")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )
    llm_model_name: str = Field(default="meta-llama/llama-3.2-3b-instruct:free")
    llm_temperature: float = Field(default=0.2)
    llm_max_tokens: int = Field(default=512)

    # -------------------------------------------------
    # Logging
    # -------------------------------------------------
    log_level: str = Field(default="INFO")
    log_file: str = Field(
        default=str(BASE_DIR / "logs" / "voxops.log"),
        description="Path for rotating log file",
    )

    # -------------------------------------------------
    # LangChain
    # -------------------------------------------------
    langchain_tracing_v2: bool = Field(default=False)
    langchain_api_key: str = Field(default="")

    # -------------------------------------------------
    # Derived / computed paths (not from env)
    # -------------------------------------------------
    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def knowledge_base_dir(self) -> Path:
        return BASE_DIR / "data" / "knowledge_base"

    @property
    def logs_dir(self) -> Path:
        return BASE_DIR / "logs"


# Singleton — import this everywhere
settings = Settings()

# Ensure required directories exist at import time
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "tts_output").mkdir(parents=True, exist_ok=True)
settings.logs_dir.mkdir(parents=True, exist_ok=True)
settings.knowledge_base_dir.mkdir(parents=True, exist_ok=True)
