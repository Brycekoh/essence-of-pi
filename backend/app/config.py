from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration, read from the environment or a .env file.

    Everything has a working default so `uvicorn app.main:app` runs on a fresh
    clone with no setup. Anything secret gets added in a later milestone.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where uploaded PDFs are written. Relative paths resolve against backend/.
    upload_dir: Path = BACKEND_ROOT / "storage" / "uploads"

    # Reject anything larger before we bother reading it. 25 MB.
    max_upload_bytes: int = 25 * 1024 * 1024

    # Comma-separated in the env, a list here.
    allowed_origins: str = "http://localhost:3000"

    # --- LLM (milestone 2) ---
    # Absent by default, so the app still boots without a key; the concept
    # endpoints return 503 with instructions instead of crashing at startup.
    gemini_api_key: str | None = None
    llm_model: str = "gemini-2.0-flash"

    # How many concepts to ask for per paper.
    max_concepts: int = 6

    # How much of the paper to send. See services/concepts.py for the reasoning.
    max_chars_to_model: int = 60_000

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the whole app shares one Settings instance.

    Tests override this via FastAPI's dependency_overrides.
    """
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings
