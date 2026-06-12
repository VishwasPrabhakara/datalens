"""Run the public Chinook text-to-SQL benchmark.

Requires GOOGLE_API_KEY. Writes aggregate and per-question JSON without
including credentials or private database content.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from agents import SQLAgent
from loop import generate_with_correction
from retrieval import SchemaRetriever
from schema_profiler import SchemaProfiler
from validator import Validator


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="chinook.db")
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("benchmarks/chinook_questions.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark_results/chinook_results.json"),
    )
    return parser.parse_args()


def canonical_rows(df: pd.DataFrame) -> list[tuple[str, ...]]:
    normalized = df.copy()
    for column in normalized.columns:
        if pd.api.types.is_numeric_dtype(normalized[column]):
            normalized[column] = normalized[column].map(
                lambda value: "" if pd.isna(value) else f"{float(value):.6f}"
            )
        else:
            normalized[column] = normalized[column].fillna("").astype(str).str.strip()
    return sorted(tuple(row) for row in normalized.astype(str).itertuples(index=False, name=None))


def execute(engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def validate_api_key(api_key: str | None) -> str:
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is required. Create a Gemini API key in Google AI "
            "Studio and add it to .env."
        )
    api_key = api_key.strip()
    if not api_key.startswith(("AIza", "AQ.")):
        raise RuntimeError(
            "GOOGLE_API_KEY does not look like a Gemini API key. Current "
            "Google AI Studio authorization keys start with 'AQ.'; older "
            "standard keys commonly start with 'AIza'."
        )
    return api_key


def main():
    args = parse_args()
    load_dotenv()
    api_key = validate_api_key(os.getenv("GOOGLE_API_KEY"))

    cases = json.loads(args.questions.read_text(encoding="utf-8"))
    engine = create_engine(f"sqlite:///{args.database}")
    profiler = SchemaProfiler(args.database, api_key=api_key)
    profiler.profile()
    retriever = SchemaRetriever(profiler.documents, api_key)
    agent = SQLAgent(api_key)
    validator = Validator(engine, dialect="sqlite")

    rows = []
    for case in cases:
        started = time.perf_counter()
        docs = retriever.retrieve(case["question"])
        generated = generate_with_correction(
            case["question"], docs, agent, validator, dialect="sqlite"
        )
        latency = time.perf_counter() - started
        first_attempt_valid = bool(
            generated.attempts and generated.attempts[0].validation.ok
        )
        execution_ok = False
        result_match = False
        error = generated.error

        if generated.ok and generated.sql:
            try:
                actual = execute(engine, generated.sql)
                expected = execute(engine, case["reference_sql"])
                execution_ok = True
                result_match = canonical_rows(actual) == canonical_rows(expected)
            except Exception as exc:
                error = str(exc)

        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "retrieved_tables": [
                    doc.metadata.get("table_name", "") for doc in docs
                ],
                "first_attempt_valid": first_attempt_valid,
                "final_valid": generated.ok,
                "execution_ok": execution_ok,
                "result_match": result_match,
                "corrections": generated.n_corrections,
                "latency_seconds": round(latency, 3),
                "generated_sql": generated.sql,
                "error": error,
            }
        )
        print(
            f"{case['id']}: valid={generated.ok} execute={execution_ok} "
            f"match={result_match} corrections={generated.n_corrections}"
        )

    total = len(rows)
    summary = {
        "questions": total,
        "first_attempt_valid_rate": sum(r["first_attempt_valid"] for r in rows) / total,
        "final_valid_rate": sum(r["final_valid"] for r in rows) / total,
        "execution_success_rate": sum(r["execution_ok"] for r in rows) / total,
        "result_match_rate": sum(r["result_match"] for r in rows) / total,
        "average_corrections": sum(r["corrections"] for r in rows) / total,
        "average_latency_seconds": sum(r["latency_seconds"] for r in rows) / total,
    }
    payload = {"summary": summary, "results": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
