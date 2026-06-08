"""Smoke test for the generate-validate-correct loop."""
from dotenv import load_dotenv
import os

from sqlalchemy import create_engine

from schema_profiler import SchemaProfiler
from retrieval import SchemaRetriever
from agents import SQLAgent
from validator import Validator, ValidationResult
from loop import generate_with_correction

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

print("Setting up...")
profiler = SchemaProfiler("chinook.db")
profiler.profile()
retriever = SchemaRetriever(profiler.documents, api_key)
agent = SQLAgent(api_key)
engine = create_engine("sqlite:///chinook.db")
validator = Validator(engine, dialect="sqlite")
print("Ready.\n")

# Test 1: Normal flow — should pass on first try most of the time
queries = [
    "Top 5 customers by total spending",
    "Average track duration by genre",
    "Which media types are used in invoices?",
]

for q in queries:
    print(f"❓ {q}")
    docs = retriever.retrieve(q)
    result = generate_with_correction(q, docs, agent, validator)

    if result.ok:
        print(f"   ✅ OK after {len(result.attempts)} attempt(s), {result.n_corrections} corrections")
        print(f"   Final SQL:")
        for line in result.sql.splitlines():
            print(f"     {line}")
    else:
        print(f"   ❌ Failed: {result.error}")
        print(f"   Attempts: {len(result.attempts)}")

    # Print trace
    for a in result.attempts:
        status = "✅" if a.validation.ok else f"❌ ({a.validation.stage})"
        print(f"   - Attempt {a.attempt_num}: {status}")
        if not a.validation.ok:
            print(f"     Error: {a.validation.error}")
    print()

# Test 2: Force a correction by using a custom validator that fails the first attempt
class FlakyValidator(Validator):
    """Fails the first call, then delegates to the real validator."""
    def __init__(self, engine, dialect):
        super().__init__(engine, dialect)
        self.calls = 0

    def validate(self, sql):
        self.calls += 1
        if self.calls == 1:
            return ValidationResult(
                ok=False,
                error="no such column: FakeColumn",
                stage="explain",
            )
        return super().validate(sql)

print("=" * 60)
print("Test 2: Forced first-attempt failure to verify correction loop")
print("=" * 60)
flaky = FlakyValidator(engine, "sqlite")
docs = retriever.retrieve("List the top 5 most popular genres")
result = generate_with_correction(
    "List the top 5 most popular genres", docs, agent, flaky
)

print(f"Final: {'✅ recovered' if result.ok else '❌ failed'}")
print(f"Attempts: {len(result.attempts)}")
for a in result.attempts:
    status = "✅" if a.validation.ok else f"❌ ({a.validation.stage})"
    print(f"  Attempt {a.attempt_num}: {status}")
    if not a.validation.ok:
        print(f"    Error: {a.validation.error}")

if result.ok:
    print(f"\nFinal SQL:\n  {result.sql}")