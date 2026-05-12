from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SGE_", extra="ignore", populate_by_name=True)

    base_url: str = "https://www.socialgrowthengineers.com"
    fetcher: Literal["auto", "http", "browser"] = "auto"
    browser_state_path: Path = Path("data/browser_state.json")
    browser_headless: bool = True

    data_dir: Path = Path("data")
    chroma_dir: Path = Path("data/chroma")
    collection_name: str = "sge_articles"
    vectorstore: Literal["chroma", "upstash"] = "chroma"
    upstash_vector_rest_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("UPSTASH_VECTOR_REST_URL", "SGE_UPSTASH_VECTOR_REST_URL"),
    )
    upstash_vector_rest_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("UPSTASH_VECTOR_REST_TOKEN", "SGE_UPSTASH_VECTOR_REST_TOKEN"),
    )

    embedding_provider: Literal["openai", "hash"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    answer_model: str = "gpt-5.4-mini"
    fast_model: str = "gpt-5.4-mini"
    deep_model: str = "gpt-5.5"

    chunk_target_tokens: int = Field(default=850, ge=200, le=2000)
    chunk_overlap_tokens: int = Field(default=120, ge=0, le=500)

    request_timeout_seconds: float = 30.0
    max_concurrency: int = Field(default=4, ge=1, le=16)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "articles").mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.browser_state_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
