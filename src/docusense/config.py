"""Settings.

Where things live:
- DOCUSENSE_HOME (default ~/.docusense) holds the local SQLite database, blobs and indexes.
- Settings are DOCUSENSE_* variables, read from the environment, then ./.env, then $DOCUSENSE_HOME/.env.
  They are namespaced so a project's own DATABASE_URL never leaks in when an MCP client launches us.
- DOCUSENSE_DATABASE_URL selects the backend: unset or sqlite:///path → embedded SQLite (no server);
  postgresql://… → Postgres + pgvector (install the `postgres` extra).
- API keys also accept their conventional names (GROQ_API_KEY, OPENROUTER_API_KEY).
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PARSER_VERSION = "docusense-parser/0.1.0"


def docusense_home() -> Path:
    return Path(os.environ.get("DOCUSENSE_HOME") or Path.home() / ".docusense").expanduser()


class Settings(BaseSettings):
    # Later files win, so a project-local .env overrides the per-user one.
    model_config = SettingsConfigDict(env_prefix="DOCUSENSE_", env_file=(docusense_home() / ".env", ".env"),
                                      extra="ignore", populate_by_name=True)

    database_url: str = ""
    store_dir: Path = Path("")

    embed_model: str = "BAAI/bge-small-en-v1.5"
    groq_api_key: str = Field("", validation_alias=AliasChoices("DOCUSENSE_GROQ_API_KEY", "GROQ_API_KEY"))
    extract_model: str = "openai/gpt-oss-120b"
    openrouter_api_key: str = Field("", validation_alias=AliasChoices("DOCUSENSE_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"))
    agent_provider: str = "openrouter"
    agent_model: str = ""
    agent_max_tool_calls: int = 15
    agent_max_tokens: int = 60000

    # MCP server
    tools: str = "all"            # all | core  (core = smaller tool list for tight agent contexts)
    add_roots: str = ""           # comma-separated folders add_document may read (default: home dir)
    http_token: str = ""          # bearer token required by `serve-mcp --http` when set

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
