"""
DataLens — SchemaProfiler.

Reads a SQLAlchemy-compatible database and produces one Document per table.
Each document contains:
  - Table name
  - Auto-generated one-sentence description (via Gemini)
  - Column names and types
  - One sample row (anonymized hints, no PII concerns for our use case)

These documents are what the retriever embeds and searches over.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DESCRIBE_MODEL = "gemini-2.5-flash"
SAMPLE_ROWS = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TableProfile:
    name: str
    columns: list[tuple[str, str]]  # [(col_name, col_type), ...]
    sample_rows: list[dict]
    description: str = ""

    def to_document(self, db_path: str) -> Document:
        """Render this table as a searchable Document."""
        col_lines = "\n".join(f"  - {c} ({t})" for c, t in self.columns)
        sample = (
            "\n".join(f"  {row}" for row in self.sample_rows[:1])
            if self.sample_rows
            else "  (empty table)"
        )
        content = (
            f"Table: {self.name}\n"
            f"Description: {self.description}\n"
            f"Columns:\n{col_lines}\n"
            f"Sample row:\n{sample}"
        )
        return Document(
            page_content=content,
            metadata={
                "table_name": self.name,
                "db_path": db_path,
                "column_names": [c for c, _ in self.columns],
                "column_types": {c: t for c, t in self.columns},
            },
        )


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


class SchemaProfiler:
    """Connects to a database, inspects it, and builds Documents for retrieval."""

    def __init__(self, db_uri: str, api_key: str | None = None):
        # db_uri can be 'chinook.db' (SQLite) or full SQLAlchemy URI
        if db_uri.endswith(".db") and "://" not in db_uri:
            db_uri = f"sqlite:///{db_uri}"
        self.db_uri = db_uri
        self.engine: Engine = create_engine(db_uri)
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY not set.")
        self.llm = ChatGoogleGenerativeAI(
            model=DESCRIBE_MODEL,
            google_api_key=self.api_key,
            temperature=0.1,
        )
        self.profiles: list[TableProfile] = []
        self.documents: list[Document] = []

    def profile(self) -> None:
        """Read the schema, sample rows, generate descriptions."""
        inspector = inspect(self.engine)
        table_names = inspector.get_table_names()

        for name in table_names:
            cols = inspector.get_columns(name)
            columns = [(c["name"], str(c["type"])) for c in cols]
            samples = self._sample_rows(name)
            description = self._describe_table(name, columns, samples)
            profile = TableProfile(
                name=name,
                columns=columns,
                sample_rows=samples,
                description=description,
            )
            self.profiles.append(profile)
            self.documents.append(profile.to_document(self.db_uri))

    # -------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------

    def _sample_rows(self, table: str, n: int = SAMPLE_ROWS) -> list[dict]:
        """Pull up to n rows. Handles empty tables gracefully."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {table} LIMIT {n}"))
                rows = [dict(r._mapping) for r in result.fetchall()]
            return rows
        except Exception:
            return []

    def _describe_table(
        self,
        table: str,
        columns: list[tuple[str, str]],
        samples: list[dict],
    ) -> str:
        """Ask Gemini for a one-sentence description of the table."""
        col_str = ", ".join(f"{c} ({t})" for c, t in columns)
        sample_str = samples[0] if samples else "(no rows)"
        prompt = (
            "Describe what this database table likely contains in ONE concise sentence. "
            "Be specific. Mention the main entity and key attributes. "
            "Do NOT start with 'This table' or 'The table'.\n\n"
            f"Table name: {table}\n"
            f"Columns: {col_str}\n"
            f"Sample row: {sample_str}\n\n"
            "One-sentence description:"
        )
        try:
            return self.llm.invoke(prompt).content.strip().rstrip(".") + "."
        except Exception as e:
            # Don't let one bad call break profiling — fall back gracefully
            return f"Table containing columns: {col_str[:120]}."