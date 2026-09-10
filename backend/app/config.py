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

    # --- Persistence (milestone 8) ---
    # Unset means the in-memory store: a fresh clone still runs with no
    # database, and loses everything on restart. Set it and papers, pages and
    # concepts survive. docker-compose.yml sets it for you.
    #   postgresql+psycopg://eop:eop@localhost:5432/essence_of_pi
    database_url: str | None = None

    # Reject anything larger before we bother reading it. 25 MB.
    max_upload_bytes: int = 25 * 1024 * 1024

    # Comma-separated in the env, a list here.
    allowed_origins: str = "http://localhost:3000"

    # --- LLM (milestone 2) ---
    # Absent by default, so the app still boots without a key; the concept
    # endpoints return 503 with instructions instead of crashing at startup.
    gemini_api_key: str | None = None
    # Pinned, not `gemini-flash-latest`: an alias silently changes the model
    # under you, which makes a measured success rate meaningless.
    llm_model: str = "gemini-3.8-flash"

    # Tried in order when the primary is busy or out of quota. The free-tier
    # limit is 20 requests per day *per model*, so a rotation multiplies the
    # daily budget in a way that retrying one model cannot.
    llm_fallback_models: str = "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash"

    @property
    def llm_models_csv(self) -> str:
        return ",".join([self.llm_model, self.llm_fallback_models])

    # How many concepts to ask for per paper.
    max_concepts: int = 6

    # How much of the paper to send. See services/concepts.py for the reasoning.
    # Lowered from 60k after 60k-character prompts drew repeated 503s on the
    # free tier while short prompts to the same model answered instantly.
    max_chars_to_model: int = 30_000

    # --- Rendering (milestone 3) ---
    videos_dir: Path = BACKEND_ROOT / "storage" / "videos"

    # Renders and audio work both happen inside this image, which carries
    # manim, LaTeX *and* ffmpeg. Build it once:
    #   docker build -f Dockerfile.render -t essence-of-pi/render:latest .
    # The upstream manimcommunity image has no ffmpeg binary, so muxing
    # narration would be impossible on it.
    renderer_image: str = "essence-of-pi/render:latest"
    renderer_docker_bin: str = "docker"

    # -ql 480p15 (seconds), -qm 720p30, -qh 1080p60 (minutes).
    render_quality: str = "-qm"

    # Ceilings on the container. These matter from milestone 4, when the code
    # being executed is written by a model.
    render_memory: str = "2g"
    render_cpus: str = "2"

    # Renders currently block the request. Milestone 6 moves them off it.
    render_timeout_seconds: float = 300.0

    # --- Generated animation (milestone 4) ---
    # Attempts at the generate-render-correct loop before giving up. Each
    # failed attempt costs one model call plus one container start.
    max_render_attempts: int = 3

    # When every attempt fails, render the hand-written title card instead so
    # the caller still gets a video.
    fallback_to_title_card: bool = True

    # --- Narration (milestone 5) ---
    # Scenes per concept. Each one costs a model call (plus corrections), so
    # this is the main lever on how fast a free-tier quota disappears.
    max_scenes: int = 3

    # Three engines, none of which spend model quota:
    #   kokoro  most human, its own 2.88 GB image
    #   piper   much lighter, lives in the render image
    #   gtts    no image at all, and sounds like a satnav
    speech_engine: str = "kokoro"

    # Kokoro lives in a separate image because it needs torch and manim does
    # not:  docker build -f Dockerfile.kokoro -t essence-of-pi/tts:kokoro .
    kokoro_image: str = "essence-of-pi/tts:kokoro"
    kokoro_voice: str = "af_bella"
    # Kokoro's convention is the inverse of Piper's: below 1.0 is slower.
    kokoro_speed: float = 0.92

    # Piper only.
    piper_voice: str = "/opt/voices/en_US-hfc_female-medium.onnx"
    speech_length_scale: float = 1.12  # >1 is slower
    # None keeps the voice's own defaults. Lower is steadier, higher is more
    # expressive and more likely to land an odd emphasis.
    speech_noise_scale: float | None = None
    speech_noise_w_scale: float | None = None

    # Both local engines. The pause between sentences is where understanding
    # happens; gTTS offers none, which is most of why it sounds relentless.
    speech_sentence_silence: float = 0.35

    # gTTS only. tld changes the accent: com (US), co.uk, com.au.
    speech_lang: str = "en"
    speech_tld: str = "com"

    # ffmpeg work is quick; a long timeout here just hides a hung container.
    media_timeout_seconds: float = 180.0

    # --- Jobs (milestone 6) ---
    # How many scenes may render at once, across every job in the process.
    # Each container gets render_cpus CPUs and render_memory, so this is a
    # statement about the machine, not about the workload.
    max_parallel_renders: int = 2

    # Finished jobs kept in memory for status polling. Running jobs are never
    # evicted regardless of this.
    job_history: int = 50

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
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    return settings
