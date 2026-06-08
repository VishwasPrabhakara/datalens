"""
DataLens — SQL Validator.

Two-stage validation:
  1. sqlglot parse  -> catches syntax errors offline
  2. EXPLAIN dry-run -> catches missing columns/tables against the live DB

Returns a structured ValidationResult that's safe to feed to the Corrector
when validation fails.
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
    stage: str = ""  # "parse" | "explain" | ""

    def __bool__(self) -> bool:
        return self.ok


class Validator:
    """Validates SQL before execution. Cheap, deterministic, no LLM calls."""

    def __init__(self, engine: Engine, dialect: str = "sqlite"):
        self.engine = engine
        self.dialect = dialect

    def validate(self, sql: str) -> ValidationResult:
        # Stage 1: syntactic check via sqlglot
        try:
            sqlglot.parse_one(sql, read=self.dialect)
        except sqlglot.errors.ParseError as e:
            return ValidationResult(
                ok=False,
                error=f"Syntax error: {e}",
                stage="parse",
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