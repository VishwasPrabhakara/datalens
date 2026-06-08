"""
DataLens — Generate-Validate-Correct loop.

Wraps SQLAgent + Validator into a single resilient call. Handles up to
MAX_RETRIES correction attempts. Returns full trace for UI display.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.documents import Document

from agents import SQLAgent
from validator import Validator, ValidationResult

MAX_RETRIES = 3


@dataclass
class Attempt:
    sql: str
    validation: ValidationResult
    attempt_num: int  # 0 = first try, 1+ = corrections


@dataclass
class GenerateResult:
    ok: bool
    sql: str | None
    attempts: list[Attempt] = field(default_factory=list)
    error: str = ""

    @property
    def n_corrections(self) -> int:
        return max(0, len(self.attempts) - 1)


def generate_with_correction(
    question: str,
    docs: list[Document],
    agent: SQLAgent,
    validator: Validator,
    dialect: str = "sqlite",
    max_retries: int = MAX_RETRIES,
) -> GenerateResult:
    """Generate SQL, validate, and self-correct up to max_retries times."""
    attempts: list[Attempt] = []

    # First attempt
    sql = agent.generate(question, docs, dialect=dialect)
    if sql.strip().upper() == "NO_ANSWER":
        return GenerateResult(
            ok=False,
            sql=None,
            error="The model could not answer this question with the available schema.",
        )
    result = validator.validate(sql)
    attempts.append(Attempt(sql=sql, validation=result, attempt_num=0))

    # Correction loop
    while not result.ok and len(attempts) <= max_retries:
        sql = agent.correct(
            question=question,
            previous_sql=sql,
            error=result.error,
            docs=docs,
            dialect=dialect,
        )
        if sql.strip().upper() == "NO_ANSWER":
            return GenerateResult(
                ok=False,
                sql=None,
                attempts=attempts,
                error="Model gave up — schema doesn't support this question.",
            )
        result = validator.validate(sql)
        attempts.append(Attempt(sql=sql, validation=result, attempt_num=len(attempts)))

    if result.ok:
        return GenerateResult(ok=True, sql=sql, attempts=attempts)

    return GenerateResult(
        ok=False,
        sql=None,
        attempts=attempts,
        error=f"Failed after {len(attempts)} attempts. Last error: {result.error}",
    )