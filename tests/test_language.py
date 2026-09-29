import pytest

from app.agent.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("This is unacceptable, I've been waiting for days", "English"),
        ("Can I talk to a real person?", "English"),
        ("Quero remarcar minha consulta para amanhã", "Portuguese"),
        ("Quando é o meu exame?", "Portuguese"),
        ("slot 12", None),  # no clear language: the model keeps the conversation's language
    ],
)
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_language_hint_reaches_the_model(db, ana):
    from app.agent.agent import Agent

    seen = []

    class Spy:
        name = "spy"

        def complete(self, system, messages, tools):
            from app.agent.llm import LLMResponse

            seen.append(system)
            return LLMResponse([{"type": "text", "text": "ok"}], {})

    Agent(db, llm=Spy()).handle(ana, "Can I talk to a real person?")
    assert "reply in English" in seen[0][1]
