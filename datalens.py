"""
DataLens — End-to-end pipeline orchestrator.

Public API:
    lens = DataLens("chinook.db", api_key=...)
    lens.connect()                  # one-time
    answer = lens.ask(question)     # per question
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from agents import SQLAgent
from insight import InsightAgent
from loop import Attempt, generate_with_correction
from retrieval import SchemaRetriever
from schema_profiler import SchemaProfiler
from validator import Validator


# ---------------------------------------------------------------------------
# Public data type returned from ask()
# ---------------------------------------------------------------------------


@dataclass
class Answer:
    question: str
    ok: bool
    sql: str | None = None
    df: pd.DataFrame | None = None
    chart: go.Figure | None = None
    chart_type: str = ""
    summary: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    retrieved_tables: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""

    @property
    def n_corrections(self) -> int:
        return max(0, len(self.attempts) - 1)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class DataLens:
    """End-to-end DataLens pipeline. One instance per database."""

    def __init__(self, db_uri: str, api_key: str | None = None):
        self.db_uri = (
            f"sqlite:///{db_uri}"
            if db_uri.endswith(".db") and "://" not in db_uri
            else db_uri
        )
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY not set.")

        self.engine: Engine = create_engine(self.db_uri)
        self.dialect = self._infer_dialect(self.db_uri)

        # Built during connect()
        self.profiler: SchemaProfiler | None = None
        self.retriever: SchemaRetriever | None = None

        # Reused across calls
        self.sql_agent = SQLAgent(self.api_key)
        self.validator = Validator(self.engine, dialect=self.dialect)
        self.insight_agent = InsightAgent(self.engine, self.api_key)

    # -------------------------------------------------------------------
    # Connection / schema indexing
    # -------------------------------------------------------------------

    def connect(self) -> None:
        """Profile the database and build the schema retriever."""
        self.profiler = SchemaProfiler(self.db_uri, api_key=self.api_key)
        self.profiler.profile()
        if not self.profiler.documents:
            raise RuntimeError(
                "No tables found. The database appears empty or unreadable."
            )
        self.retriever = SchemaRetriever(self.profiler.documents, self.api_key)

    @property
    def is_connected(self) -> bool:
        return self.retriever is not None

    @property
    def table_count(self) -> int:
        return len(self.profiler.documents) if self.profiler else 0

    @property
    def table_summaries(self) -> dict[str, str]:
        if not self.profiler:
            return {}
        return {p.name: p.description for p in self.profiler.profiles}

    # -------------------------------------------------------------------
    # Question answering
    # -------------------------------------------------------------------

    def ask(self, question: str) -> Answer:
        if not self.is_connected:
            return Answer(
                question=question,
                ok=False,
                error="DataLens not connected. Call connect() first.",
            )

        # Step A: retrieve relevant tables
        docs = self.retriever.retrieve(question)
        retrieved_tables = [d.metadata["table_name"] for d in docs]

        # Step B: generate + validate + correct
        gen_result = generate_with_correction(
            question=question,
            docs=docs,
            agent=self.sql_agent,
            validator=self.validator,
            dialect=self.dialect,
        )

        if not gen_result.ok or not gen_result.sql:
            return Answer(
                question=question,
                ok=False,
                attempts=gen_result.attempts,
                retrieved_tables=retrieved_tables,
                error=gen_result.error or "Could not produce a valid SQL query.",
            )

        # Step C: execute + insight
        try:
            insight = self.insight_agent.run(gen_result.sql, question)
        except Exception as e:
            return Answer(
                question=question,
                ok=False,
                sql=gen_result.sql,
                attempts=gen_result.attempts,
                retrieved_tables=retrieved_tables,
                error=f"Query executed but insight failed: {e}",
            )

        return Answer(
            question=question,
            ok=True,
            sql=gen_result.sql,
            df=insight.df,
            chart=insight.chart,
            chart_type=insight.chart_type,
            summary=insight.summary,
            attempts=gen_result.attempts,
            retrieved_tables=retrieved_tables,
        )

    # -------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------

    @staticmethod
    def _infer_dialect(db_uri: str) -> str:
        if db_uri.startswith("sqlite"):
            return "sqlite"
        if db_uri.startswith("postgres"):
            return "postgres"
        if db_uri.startswith("mysql"):
            return "mysql"
        return "sqlite"