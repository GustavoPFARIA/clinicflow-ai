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
