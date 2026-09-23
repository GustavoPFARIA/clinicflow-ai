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
                id="call_1", function=SimpleNamespace(name="search_knowledge_base", arguments='{"query": "Unimed"}')
            )
            message = SimpleNamespace(content=None, tool_calls=[call])
        else:
            message = SimpleNamespace(content="Yes, we accept Unimed.", tool_calls=None)
        usage = SimpleNamespace(
            prompt_tokens=300, completion_tokens=12, prompt_tokens_details=SimpleNamespace(cached_tokens=256)
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def test_openai_provider_runs_the_same_agent_loop(db, ana):
    from app.agent.llm import OpenAILLM

    llm = OpenAILLM.__new__(OpenAILLM)
    fake = FakeCompletions()
    llm.client, llm.model, llm.name = SimpleNamespace(chat=SimpleNamespace(completions=fake)), "gpt-test", "gpt-test"

    result = Agent(db, llm=llm).handle(ana, "Do you accept Unimed? My CPF is 123.456.789-09")

    assert [t.tool for t in result.trace] == ["search_knowledge_base"]
    assert result.reply == "Yes, we accept Unimed."
    first, second = fake.calls
    assert first["messages"][0]["role"] == "system"
    assert first["tools"][0]["type"] == "function"
    assert "123.456.789-09" not in str(first["messages"])  # redaction is provider-independent
    roles = [m["role"] for m in second["messages"]]
    assert roles[-2:] == ["assistant", "tool"] and second["messages"][-1]["tool_call_id"] == "call_1"
    assert result.usage["cache_read_input_tokens"] == 512
