from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PARSER_VERSION = "docusense-parser/0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql://docusense:docusense@localhost:5433/docusense"
    store_dir: Path = PROJECT_ROOT / "store"

    embed_model: str = "BAAI/bge-small-en-v1.5"
    groq_api_key: str = ""
    extract_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str = ""
    agent_provider: str = "openrouter"
    agent_model: str = ""
    agent_max_tool_calls: int = 15
    agent_max_tokens: int = 60000

    @property
    def blob_dir(self) -> Path:
        path = self.store_dir if self.store_dir.is_absolute() else PROJECT_ROOT / self.store_dir
        return path / "blobs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
