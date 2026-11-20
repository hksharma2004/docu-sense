"""settings.

- DOCUSENSE_HOME (default ~/.docusense) holds the sqlite db, blobs and indexes
- vars are DOCUSENSE_*, read from env, then ./.env, then $DOCUSENSE_HOME/.env.
  namespaced so a project's own DATABASE_URL never leaks in via an mcp client
- DOCUSENSE_DATABASE_URL picks the backend: unset or sqlite:///path = embedded sqlite,
  postgresql://... = postgres + pgvector (needs the `postgres` extra)
- api keys also accept their usual names (GROQ_API_KEY, OPENROUTER_API_KEY)
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PARSER_VERSION = "docusense-parser/0.2.0"  # 0.2: multi-column pdfs, docx/html. single-column output unchanged


def docusense_home() -> Path:
    return Path(os.environ.get("DOCUSENSE_HOME") or Path.home() / ".docusense").expanduser()


class Settings(BaseSettings):
    # later files win, so a project .env overrides the per-user one
    model_config = SettingsConfigDict(env_prefix="DOCUSENSE_", env_file=(docusense_home() / ".env", ".env"),
                                      extra="ignore", populate_by_name=True)

    database_url: str = ""
    store_dir: Path = Path("")

    embed_model: str = "BAAI/bge-small-en-v1.5"
    groq_api_key: str = Field("", validation_alias=AliasChoices("DOCUSENSE_GROQ_API_KEY", "GROQ_API_KEY"))
    extract_model: str = "openai/gpt-oss-120b"
    # llm provider for the bounded fallbacks (see llm.py)
    llm_provider: str = "auto"    # auto | groq | anthropic | openai | ollama | openai-compatible | none
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    anthropic_api_key: str = Field("", validation_alias=AliasChoices("DOCUSENSE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"))
    openai_api_key: str = Field("", validation_alias=AliasChoices("DOCUSENSE_OPENAI_API_KEY", "OPENAI_API_KEY"))
    openrouter_api_key: str = Field("", validation_alias=AliasChoices("DOCUSENSE_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"))
    agent_provider: str = "openrouter"
    agent_model: str = ""
    agent_max_tool_calls: int = 15
    agent_max_tokens: int = 60000

    # mcp server
    tools: str = "all"            # all | core (core = smaller tool list for tight contexts)
    add_roots: str = ""           # comma-separated folders add_document may read (default: home)
    http_token: str = ""          # bearer token for `serve-mcp --http`, if set

    @property
    def home(self) -> Path:
        return docusense_home()

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.home / 'docusense.db'}"

    @property
    def resolved_store_dir(self) -> Path:
        if str(self.store_dir) in ("", "."):
            return self.home / "store"
        return self.store_dir.expanduser().resolve()

    @property
    def blob_dir(self) -> Path:
        return self.resolved_store_dir / "blobs"

    @property
    def index_dir(self) -> Path:
        return self.resolved_store_dir / "index"


@lru_cache
def get_settings() -> Settings:
    return Settings()
