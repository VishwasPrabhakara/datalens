"""
DataLens — Agents.

Currently houses SQLAgent (generates SQL from retrieved schema).
Future agents (Validator, Corrector, Insight) live here too.
"""
from __future__ import annotations

import os
import re

from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI

from prompts import SQL_PROMPT, CORRECTION_PROMPT

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SQL_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# SQL Agent
# ---------------------------------------------------------------------------


def _docs_to_schema_block(docs: list[Document]) -> str:
    """Render retrieved table Documents as a clean schema block for the prompt."""
    blocks = []
    for doc in docs:
        # Document content already has name + description + columns + sample row,
        # so we just pass it through as-is.
        blocks.append(doc.page_content)
    return "\n\n".join(blocks)


def _clean_sql(raw: str) -> str:
    """Strip markdown code fences, leading/trailing whitespace, trailing semicolons."""
    text = raw.strip()
    # Strip ```sql ... ``` or ``` ... ``` fences if Gemini ignores the no-fences rule
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip().rstrip(";").strip()
    return text


class SQLAgent:
    """Generates SQL queries from a natural-language question + retrieved schema."""

    def __init__(self, api_key: str | None = None, model: str = SQL_MODEL):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY not set.")
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=self.api_key,
            temperature=0.1,
        )

    def generate(
        self,
        question: str,
        docs: list[Document],
        dialect: str = "sqlite",
    ) -> str:
        """Generate a SQL query. Returns 'NO_ANSWER' if not answerable."""
        schema = _docs_to_schema_block(docs)
        prompt = SQL_PROMPT.format(
            question=question,
            schema=schema,
            dialect=dialect,
        )
        raw = self.llm.invoke(prompt).content
        return _clean_sql(raw)

    def correct(
        self,
        question: str,
        previous_sql: str,
        error: str,
        docs: list[Document],
        dialect: str = "sqlite",
    ) -> str:
        """Regenerate SQL after a validation failure. Used by Step 6's CorrectorAgent."""
        schema = _docs_to_schema_block(docs)
        prompt = CORRECTION_PROMPT.format(
            question=question,
            previous_sql=previous_sql,
            error=error,
            schema=schema,
            dialect=dialect,
        )
        raw = self.llm.invoke(prompt).content
        return _clean_sql(raw)