"""
DataLens — InsightAgent.

Runs validated SQL, picks the right chart type heuristically, and generates
a short plain-language summary with Gemini.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prompts import INSIGHT_PROMPT

INSIGHT_MODEL = "gemini-2.5-flash"
MAX_BAR_CATEGORIES = 25
RESULT_PREVIEW_ROWS = 10


@dataclass
class Insight:
    df: pd.DataFrame
    chart: go.Figure | None
    chart_type: str  # "bar" | "line" | "scatter" | "table" | "single_value"
    summary: str
    row_count: int


class InsightAgent:
    def __init__(self, engine: Engine, api_key: str | None = None):
        self.engine = engine
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY not set.")
        self.llm = ChatGoogleGenerativeAI(
            model=INSIGHT_MODEL,
            google_api_key=self.api_key,
            temperature=0.2,
        )

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def run(self, sql: str, question: str) -> Insight:
        df = self._execute(sql)
        chart_type = self._pick_chart_type(df)
        chart = self._build_chart(df, chart_type)
        summary = self._summarize(question, sql, df)
        return Insight(
            df=df,
            chart=chart,
            chart_type=chart_type,
            summary=summary,
            row_count=len(df),
        )

    # -------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------

    def _execute(self, sql: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def _pick_chart_type(self, df: pd.DataFrame) -> str:
        n_rows, n_cols = df.shape

        if n_rows == 0:
            return "table"

        if n_rows == 1 and n_cols == 1:
            return "single_value"

        if n_cols > 5:
            return "table"

        # Identify column kinds
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        datetime_cols = self._detect_datetime_cols(df)
        text_cols = [
            c for c in df.columns
            if c not in numeric_cols and c not in datetime_cols
        ]

        # Time series: one datetime + at least one numeric
        if datetime_cols and numeric_cols:
            return "line"

        # Scatter: two numeric, no categorical (rare in SQL output but possible)
        if len(numeric_cols) >= 2 and not text_cols and not datetime_cols:
            return "scatter"

        # Bar: at least one categorical + one numeric, manageable cardinality.
        # Multiple text columns will be concatenated into a single label in _build_chart.
        if (
            len(text_cols) >= 1
            and len(numeric_cols) >= 1
            and n_rows <= MAX_BAR_CATEGORIES
        ):
            return "bar"

        # Fallback
        return "table"

    def _detect_datetime_cols(self, df: pd.DataFrame) -> list[str]:
        """Find columns that look like dates (pandas dtype OR parseable strings)."""
        detected = list(df.select_dtypes(include=["datetime", "datetimetz"]).columns)
        for col in df.columns:
            if col in detected:
                continue
            if df[col].dtype == "object":
                try:
                    parsed = pd.to_datetime(df[col], errors="raise")
                    if parsed.notna().sum() / len(df) > 0.8:
                        detected.append(col)
                except Exception:
                    pass
        return detected

    def _build_chart(self, df: pd.DataFrame, chart_type: str) -> go.Figure | None:
        if chart_type in ("table", "single_value") or df.empty:
            return None

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        datetime_cols = self._detect_datetime_cols(df)
        text_cols = [
            c for c in df.columns
            if c not in numeric_cols and c not in datetime_cols
        ]

        try:
            if chart_type == "line" and datetime_cols and numeric_cols:
                return px.line(df, x=datetime_cols[0], y=numeric_cols[0])
            if chart_type == "bar" and text_cols and numeric_cols:
                plot_df = df.copy()
                if len(text_cols) > 1:
                    # Combine multiple text columns into a single label
                    # (e.g., FirstName + LastName -> "Helena Holý")
                    plot_df["_label"] = plot_df[text_cols].astype(str).agg(" ".join, axis=1)
                    x_col = "_label"
                else:
                    x_col = text_cols[0]
                return px.bar(
                    plot_df,
                    x=x_col,
                    y=numeric_cols[0],
                    labels={x_col: " / ".join(text_cols), numeric_cols[0]: numeric_cols[0]},
                ).update_layout(xaxis_tickangle=-30)
            if chart_type == "scatter" and len(numeric_cols) >= 2:
                return px.scatter(df, x=numeric_cols[0], y=numeric_cols[1])
        except Exception:
            return None
        return None

    def _summarize(self, question: str, sql: str, df: pd.DataFrame) -> str:
        if df.empty:
            return "The query returned no rows. The data may not contain matches for this question."

        preview = df.head(RESULT_PREVIEW_ROWS).to_string(index=False)
        schema_context = self._schema_context(df)
        prompt = INSIGHT_PROMPT.format(
            question=question,
            sql=sql,
            schema_context=schema_context,
            result_preview=preview,
        )
        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception:
            return f"Query returned {len(df)} rows."

    def _schema_context(self, df: pd.DataFrame) -> str:
        """Render the result column names + dtypes for the summary prompt."""
        lines = []
        for col, dtype in df.dtypes.items():
            lines.append(f"  - {col} ({dtype})")
        return "\n".join(lines)