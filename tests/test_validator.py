import pytest
from sqlalchemy import create_engine, text

from validator import Validator


@pytest.fixture()
def engine():
    db = create_engine("sqlite:///:memory:")
    with db.begin() as conn:
        conn.execute(text("CREATE TABLE artists (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO artists (name) VALUES ('A'), ('B'), ('C')"))
    return db


@pytest.fixture()
def validator(engine):
    return Validator(engine, dialect="sqlite")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM artists",
        "WITH named AS (SELECT name FROM artists) SELECT * FROM named",
        "SELECT name FROM artists UNION ALL SELECT name FROM artists",
    ],
)
def test_allows_read_only_queries(validator, sql):
    assert validator.validate(sql).ok


@pytest.mark.parametrize(
    ("sql", "expected_stages"),
    [
        ("INSERT INTO artists (name) VALUES ('D')", {"policy"}),
        ("UPDATE artists SET name = 'X'", {"policy"}),
        ("DELETE FROM artists", {"policy"}),
        ("DROP TABLE artists", {"policy"}),
        ("CREATE TABLE secrets (value TEXT)", {"policy"}),
        ("PRAGMA table_info(artists)", {"policy"}),
        ("ATTACH DATABASE 'other.db' AS other", {"parse", "policy"}),
    ],
)
def test_rejects_non_read_only_statements(validator, sql, expected_stages):
    result = validator.validate(sql)
    assert not result.ok
    assert result.stage in expected_stages


def test_rejects_multiple_statements(validator):
    result = validator.validate("SELECT * FROM artists; DROP TABLE artists")
    assert not result.ok
    assert result.stage == "policy"


def test_reports_semantic_database_errors(validator):
    result = validator.validate("SELECT missing_column FROM artists")
    assert not result.ok
    assert result.stage == "explain"
    assert "missing_column" in result.error


def test_rejected_statement_does_not_modify_database(engine, validator):
    assert not validator.validate("DELETE FROM artists").ok
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM artists")).scalar_one()
    assert count == 3
