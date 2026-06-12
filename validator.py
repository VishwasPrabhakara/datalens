"""
DataLens — SQL Validator.

Two-stage validation:
  1. sqlglot parse  -> catches syntax errors offline
  2. EXPLAIN dry-run -> catches missing columns/tables against the live DB

Only a single read-only query is accepted. Returns a structured
ValidationResult that's safe to feed to the Corrector when validation fails.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class ValidationResult:
    ok: bool
    error: str = ""
    stage: str = ""  # "parse" | "policy" | "explain" | ""

    def __bool__(self) -> bool:
        return self.ok


class Validator:
    """Validates SQL before execution. Cheap, deterministic, no LLM calls."""

    def __init__(self, engine: Engine, dialect: str = "sqlite"):
        self.engine = engine
        self.dialect = dialect

    def validate(self, sql: str) -> ValidationResult:
        # Stage 1: parse exactly one statement.
        try:
            statements = [
                statement
                for statement in sqlglot.parse(sql, read=self.dialect)
                if statement is not None
            ]
        except sqlglot.errors.ParseError as e:
            return ValidationResult(
                ok=False,
                error=f"Syntax error: {e}",
                stage="parse",
            )

        if len(statements) != 1:
            return ValidationResult(
                ok=False,
                error="Exactly one SQL statement is allowed.",
                stage="policy",
            )

        statement = statements[0]
        if not _is_read_only_query(statement):
            return ValidationResult(
                ok=False,
                error="Only read-only SELECT queries are allowed.",
                stage="policy",
            )

        # Stage 2: semantic check via EXPLAIN
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"EXPLAIN {sql}"))
        except SQLAlchemyError as e:
            return ValidationResult(
                ok=False,
                error=_clean_db_error(str(e)),
                stage="explain",
            )

        return ValidationResult(ok=True)


def _is_read_only_query(statement: sqlglot.Expression) -> bool:
    """Allow query expressions while rejecting DML, DDL and commands."""
    forbidden = tuple(
        expression_type
        for name in (
            "Insert",
            "Update",
            "Delete",
            "Create",
            "Drop",
            "Alter",
            "Command",
            "Transaction",
            "Commit",
            "Rollback",
            "Merge",
            "Copy",
        )
        if (expression_type := getattr(sqlglot.exp, name, None)) is not None
    )
    if isinstance(statement, forbidden):
        return False
    if any(statement.find(expression_type) is not None for expression_type in forbidden):
        return False
    return isinstance(statement, sqlglot.exp.Query)


def _clean_db_error(raw: str) -> str:
    """Strip noisy SQLAlchemy wrapping so the Corrector sees a clear message."""
    # SQLAlchemy errors usually look like:
    #   '(sqlite3.OperationalError) no such column: NonExistent\n[SQL: EXPLAIN ...]'
    # We keep the first line, drop the SQL echo.
    first_line = raw.splitlines()[0] if raw else raw
    # Strip the leading "(driver.ErrorClass) " prefix when present
    if first_line.startswith("(") and ")" in first_line:
        first_line = first_line.split(")", 1)[1].strip()
    return first_line.strip()
