from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret_key: str
    fernet_key: str
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    app_base_url: str = "http://localhost:8000"
    allowed_emails: str = ""
    max_duration_seconds: int = 14400
    max_transcription_size_bytes: int = 100 * 1024 * 1024
    audio_storage_path: str = "./data/audio"
    log_level: str = "INFO"
    listen_notes_api_key: str = ""

    # ── TTS defaults (used when UserSettings.tts_voice_* is null) ────────
    elevenlabs_tts_default_voice_a: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    elevenlabs_tts_default_voice_b: str = "AZnzlk1XvdvUeBnXmlld"  # Domi
    elevenlabs_tts_model_id: str = "eleven_turbo_v2_5"

    # ── Personal podcast feed (GitHub Pages) ─────────────────────────────
    # Empty values disable the audio feature; the API will return 503 and
    # the UI hides the "Generate audio" button (see GET /api/me).
    github_pat: str = ""
    github_audio_repo: str = ""        # e.g. "octocat/podking-audio"
    github_audio_base_url: str = ""    # e.g. "https://octocat.github.io/podking-audio"
    podking_feed_owner_email: str = ""

    # Path to a Netscape-format cookies file for yt-dlp. YouTube increasingly
    # blocks server IPs with "Sign in to confirm you're not a bot"; passing
    # cookies from a logged-in browser session is the supported workaround.
    # See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp
    yt_dlp_cookies_file: str = ""

    # Raw Netscape-format cookies content. Useful on PaaS like Railway where
    # mounting files is awkward — paste the file body into a multi-line env
    # var and the app materializes it to a temp file at first use. Ignored
    # when yt_dlp_cookies_file is set.
    yt_dlp_cookies: str = ""

    # URL of a bgutil-ytdlp-pot-provider HTTP server. Required on datacenter
    # IPs (Railway, AWS, GCP) where YouTube rejects requests despite valid
    # cookies. Deploy brainicism/bgutil-ytdlp-pot-provider as a sidecar and
    # point this at its internal URL, e.g.
    #   http://bgutil-provider.railway.internal:4416
    yt_dlp_pot_provider_url: str = ""

    # When true, registers a /test/login endpoint that mints a session
    # cookie for any allowlisted email — used by Playwright e2e to skip
    # the Google OAuth flow. NEVER enable in production.
    test_mode: bool = False

    @field_validator("database_url", mode="before")
    @classmethod
    def _add_asyncpg_driver(cls, v: object) -> object:
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def allowed_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
