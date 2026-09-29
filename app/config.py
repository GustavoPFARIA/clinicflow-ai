from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every external service is optional: when a key is
    missing the app falls back to a local, deterministic implementation. For the
    LLM, "auto" uses whichever key is configured (Gemini has a free tier), and the
    offline scripted policy runs only when there is none (tests and CI)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ClinicFlow AI"
    database_url: str = "sqlite:///./clinicflow.db"
    public_base_url: str = "http://localhost:8000"

    # LLM
    llm_provider: str = "auto"  # "auto" | "anthropic" | "openai" | "gemini" | "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    # Any OpenAI-compatible server: Ollama (http://localhost:11434/v1), Groq, OpenRouter, vLLM...
    openai_base_url: str | None = None
    # Google Gemini free tier (no card): https://aistudio.google.com/apikey
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    # Tried in order when the main model is overloaded (503) or rate-limited (429).
    gemini_fallback_models: list[str] = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    # Minimum seconds between model calls (free-tier limits). Unset = provider default.
    llm_min_interval_s: float | None = None
    llm_timeout_s: float = 60
    llm_max_retries: int = 3
    agent_max_steps: int = 6

    # RAG
    embedding_provider: str = "hashing"  # "hashing" | "fastembed"

    # Stripe
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str = "whsec_demo_secret"
    consultation_price_cents: int = 25000
    currency: str = "brl"

    # WhatsApp Cloud API
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_verify_token: str = "clinicflow-verify"

    # n8n / automations
    automation_token: str = "dev-automation-token"
    n8n_event_webhook_url: str | None = None

    def resolved_provider(self) -> str:
        if self.llm_provider != "auto":
            return self.llm_provider
        for provider, key in (
            ("anthropic", self.anthropic_api_key),
            ("openai", self.openai_api_key),
            ("gemini", self.gemini_api_key),
        ):
            if key:
                return provider
        return "mock"

    @property
    def demo_mode(self) -> bool:
        return self.resolved_provider() == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
