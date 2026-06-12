from langchain_core.documents import Document

from loop import generate_with_correction
from validator import ValidationResult


DOCS = [Document(page_content="TABLE artists(id INTEGER, name TEXT)")]


class StubAgent:
    def __init__(self, generated, corrected=None):
        self.generated = generated
        self.corrected = corrected or generated
        self.corrections = 0

    def generate(self, question, docs, dialect):
        return self.generated

    def correct(self, question, previous_sql, error, docs, dialect):
        self.corrections += 1
        return self.corrected


class StubValidator:
    def __init__(self, results):
        self.results = iter(results)

    def validate(self, sql):
        return next(self.results)


def test_returns_first_valid_query_without_correction():
    agent = StubAgent("SELECT name FROM artists")
    validator = StubValidator([ValidationResult(ok=True)])

    result = generate_with_correction("List artists", DOCS, agent, validator)

    assert result.ok
    assert result.sql == "SELECT name FROM artists"
    assert result.n_corrections == 0


def test_corrects_invalid_query():
    agent = StubAgent("SELECT bad FROM artists", "SELECT name FROM artists")
    validator = StubValidator(
        [
            ValidationResult(ok=False, error="no such column: bad", stage="explain"),
            ValidationResult(ok=True),
        ]
    )

    result = generate_with_correction("List artists", DOCS, agent, validator)

    assert result.ok
    assert result.sql == "SELECT name FROM artists"
    assert result.n_corrections == 1
    assert agent.corrections == 1


def test_stops_when_model_returns_no_answer():
    result = generate_with_correction(
        "Delete everything",
        DOCS,
        StubAgent("NO_ANSWER"),
        StubValidator([]),
    )

    assert not result.ok
    assert result.sql is None
    assert not result.attempts
