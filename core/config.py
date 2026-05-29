from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM — Anthropic Claude (primary)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # LLM — Infomaniak AI Services (fallback souverain, hébergé en Suisse)
    infomaniak_api_key: str = Field(default="", alias="INFOMANIAK_API_KEY")
    infomaniak_product_id: str = Field(default="", alias="INFOMANIAK_PRODUCT_ID")
    infomaniak_model: str = Field(default="mistralai/Ministral-3-14B-Instruct-2512", alias="INFOMANIAK_MODEL")
    # Endpoint: https://api.infomaniak.com/2/ai/{product_id}/openai/v1/

    # MCP
    i14y_mcp_url: str = Field(
        default="https://mcp.i14y.d.c.bfs.admin.ch/mcp", alias="I14Y_MCP_URL"
    )
    mock_mcp_url: str = Field(default="http://localhost:8002/mcp", alias="MOCK_MCP_URL")

    # Ports
    fastapi_port: int = Field(default=8000, alias="FASTAPI_PORT")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")
    mock_mcp_port: int = Field(default=8002, alias="MOCK_MCP_PORT")
    open_webui_port: int = Field(default=8080, alias="OPEN_WEBUI_PORT")

    # Storage
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    cache_db_path: Path = Field(default=Path("data/cache.db"), alias="CACHE_DB_PATH")
    faiss_index_path: Path = Field(default=Path("data/faiss.index"), alias="FAISS_INDEX_PATH")
    mock_db_path: Path = Field(default=Path("data/mock.db"), alias="MOCK_DB_PATH")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def llm_model(self) -> str:
        if self.anthropic_api_key:
            return "claude-sonnet-4-6"
        if self.infomaniak_api_key and self.infomaniak_product_id:
            return f"openai/{self.infomaniak_model}"
        raise RuntimeError("No LLM configured: set ANTHROPIC_API_KEY or INFOMANIAK_API_KEY+INFOMANIAK_PRODUCT_ID in .env")

    @property
    def infomaniak_base_url(self) -> str:
        return f"https://api.infomaniak.com/2/ai/{self.infomaniak_product_id}/openai/v1"

    @property
    def using_claude(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def using_infomaniak(self) -> bool:
        return bool(self.infomaniak_api_key and self.infomaniak_product_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
