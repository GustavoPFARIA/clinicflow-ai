from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every external service is optional: when a key is
    missing the app falls back to a local, deterministic implementation so the
    whole system runs offline (demo mode)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ClinicFlow AI"
    database_url: str = "sqlite:///./clinicflow.db"
    public_base_url: str = "http://localhost:8000"

    # LLM
    llm_provider: str = "mock"  # "mock" | "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    agent_max_steps: int = 6

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

    @property
    def demo_mode(self) -> bool:
        return self.llm_provider == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
