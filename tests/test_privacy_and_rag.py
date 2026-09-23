import pytest

from app.privacy import Redactor
from app.rag.retriever import HybridRetriever, chunk_markdown


@pytest.mark.parametrize(
    "text,label",
    [
        ("CPF 123.456.789-09", "CPF"),
        ("cpf 12345678909", "CPF"),
        ("mail me at john.doe+x@clinic.com.br", "EMAIL"),
        ("call (62) 99111-0001", "PHONE"),
        ("+55 62 991110001", "PHONE"),
        ("card 4242 4242 4242 4242", "CARD"),
    ],
)
def test_redaction(text, label):
    r = Redactor()
    redacted = r.redact(text)
    assert f"[{label}_1]" in redacted
    assert r.restore(redacted) == text


def test_redaction_is_stable_within_a_conversation():
    r = Redactor()
    a = r.redact("123.456.789-09")
    b = r.redact("again 123.456.789-09 and 987.654.321-00")
    assert a == "[CPF_1]" and b == "again [CPF_1] and [CPF_2]"


def test_chunking_splits_on_h2():
    chunks = chunk_markdown("# Title\n\n## A\nalpha\n\n## B\nbeta\n## Empty\n")
    assert chunks == [("A", "alpha"), ("B", "beta")]


@pytest.mark.parametrize(
    "query,expected_heading",
    [
        ("do I have to fast for a cholesterol exam", "Blood test fasting"),
        ("what insurance plans do you take", "Health insurance"),
        ("where can I park my car", "Location and parking"),
        ("can I get my money back if I cancel", "Cancellation and rescheduling policy"),
        ("pelvic ultrasound water", "Abdominal ultrasound preparation"),
    ],
)
def test_hybrid_retrieval_top1(db, query, expected_heading):
    hits = HybridRetriever(db).search(query, k=3)
    assert hits[0].heading == expected_heading


def test_irrelevant_query_returns_nothing(db):
    assert HybridRetriever(db).search("who won the world cup in 1970", k=3) == []
