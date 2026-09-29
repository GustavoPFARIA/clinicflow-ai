"""Checks the exact request sent to the Anthropic API, without calling it."""

from types import SimpleNamespace

from app.agent.agent import Agent
from app.agent.llm import AnthropicLLM


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(model_dump=lambda include: {"type": "text", "text": "Hello Ana!"})
        usage = SimpleNamespace(
            input_tokens=50, output_tokens=5, cache_read_input_tokens=900, cache_creation_input_tokens=0
        )
        return SimpleNamespace(content=[block], usage=usage)


def make_llm() -> tuple[AnthropicLLM, FakeMessages]:
    llm = AnthropicLLM.__new__(AnthropicLLM)
    fake = FakeMessages()
    llm.client, llm.model, llm.name = SimpleNamespace(messages=fake), "claude-sonnet-5", "claude-sonnet-5"
    return llm, fake


def test_static_prompt_is_cached_and_patient_context_is_not(db, ana):
    llm, fake = make_llm()
    result = Agent(db, llm=llm).handle(ana, "hi, my CPF is 123.456.789-09")

    request = fake.calls[0]
    static, context = request["system"]
    assert static["cache_control"] == {"type": "ephemeral"}
    assert "Ana" not in static["text"]  # cache key must be identical for every patient
    assert "cache_control" not in context and "Ana" in context["text"]
    assert {t["name"] for t in request["tools"]} >= {"book_appointment", "search_knowledge_base"}
    assert "123.456.789-09" not in str(request["messages"])
    assert result.usage["cache_read_input_tokens"] == 900


class FakeCompletions:
    """Returns a tool call first, then a final answer, like a real model would."""

    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            call = SimpleNamespace(
                id="call_1",
                type="function",
                function=SimpleNamespace(name="search_knowledge_base", arguments='{"query": "Unimed"}'),
                model_extra={"extra_content": {"google": {"thought_signature": "sig-1"}}},
            )
            message = SimpleNamespace(content=None, tool_calls=[call])
        else:
            message = SimpleNamespace(content="Yes, we accept Unimed.", tool_calls=None)
        usage = SimpleNamespace(
            prompt_tokens=300, completion_tokens=12, prompt_tokens_details=SimpleNamespace(cached_tokens=256)
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def test_openai_provider_runs_the_same_agent_loop(db, ana):

    fake = FakeCompletions()
    llm = _adapter(fake)

    result = Agent(db, llm=llm).handle(ana, "Do you accept Unimed? My CPF is 123.456.789-09")

    assert [t.tool for t in result.trace] == ["search_knowledge_base"]
    assert result.reply == "Yes, we accept Unimed."
    first, second = fake.calls
    assert first["messages"][0]["role"] == "system"
    assert first["tools"][0]["type"] == "function"
    assert "123.456.789-09" not in str(first["messages"])  # redaction is provider-independent
    roles = [m["role"] for m in second["messages"]]
    assert roles[-2:] == ["assistant", "tool"] and second["messages"][-1]["tool_call_id"] == "call_1"
    # Gemini 3 thought signatures are sent back with the tool call they came with
    assert second["messages"][-2]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig-1"}}
    assert result.usage["cache_read_input_tokens"] == 512


def _adapter(completions, fallback=None):
    from app.agent.llm import OpenAILLM

    llm = OpenAILLM.__new__(OpenAILLM)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    llm.model = llm.name = "gpt-test"
    llm.fallback_models, llm.min_interval_s, llm.cooldown_s, llm._cooldown_until = fallback or [], 0.0, 120.0, {}
    return llm


def test_overloaded_model_falls_back_to_the_next_one():
    import httpx
    import openai

    class Overloaded(FakeCompletions):
        def create(self, **kwargs):
            if kwargs["model"] == "gpt-test":
                req = httpx.Request("POST", "https://example.test")
                raise openai.InternalServerError("overloaded", response=httpx.Response(503, request=req), body=None)
            return super().create(**kwargs)

    fake = Overloaded()
    resp = _adapter(fake, fallback=["lite"]).complete(["s"], [{"role": "user", "content": "hi"}], [])
    assert resp.usage["model"] == "lite" and fake.calls[0]["model"] == "lite"


def test_auto_provider_uses_the_configured_key():
    from app.config import Settings

    assert Settings(_env_file=None, llm_provider="auto").resolved_provider() == "mock"
    assert Settings(_env_file=None, llm_provider="auto", gemini_api_key="g").resolved_provider() == "gemini"
    assert Settings(
        _env_file=None, llm_provider="auto", gemini_api_key="g", anthropic_api_key="a"
    ).resolved_provider() == ("anthropic")


def test_model_outage_never_crashes_the_chat(client, db):
    """Invalid key, quota exhausted or provider down: the patient gets a polite reply
    and a human takes over, instead of an HTTP 500."""
    from unittest.mock import patch

    from sqlalchemy import select

    from app.models import TimelineEvent
    from tests.conftest import ANA

    class Down:
        name = "down"

        def complete(self, *_):
            raise RuntimeError("Please pass a valid API key")

    with patch("app.agent.agent.get_llm", return_value=Down()):
        r = client.post("/api/chat", json={"phone": ANA, "message": "Do you accept Unimed?"})
    assert r.status_code == 200
    body = r.json()
    assert "our team" in body["reply"] and body["guardrail"] == "llm_unavailable"
    kinds = db.scalars(select(TimelineEvent.kind)).all()
    assert "handoff.requested" in kinds
