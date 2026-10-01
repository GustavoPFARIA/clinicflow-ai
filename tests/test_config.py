"""The documented setup path must work: `cp .env.example .env` and start."""

from pathlib import Path

from app.config import Settings

EXAMPLE = Path(__file__).parents[1] / ".env.example"


def test_env_example_loads_with_defaults():
    s = Settings(_env_file=EXAMPLE)
    assert s.gemini_api_key is None and s.openai_base_url is None  # blank lines mean "not set"
    assert s.resolved_provider() == "mock"  # no key in the example: offline policy, nothing breaks
