"""End-to-end test of the DataLens pipeline."""
from dotenv import load_dotenv

from datalens import DataLens

load_dotenv()

print("Connecting to chinook.db...")
lens = DataLens("chinook.db")
lens.connect()
print(f"Connected. {lens.table_count} tables indexed.\n")

questions = [
    "Which 5 customers spent the most?",
    "What's the total revenue per genre?",
    "Show me invoice totals by month",
    "What's the average invoice total?",
    "Which artist has the most tracks?",
]

for q in questions:
    print(f"{'=' * 70}")
    print(f"❓ {q}")
    print(f"{'=' * 70}")
    answer = lens.ask(q)

    if not answer.ok:
        print(f"❌ {answer.error}")
        if answer.attempts:
            print(f"   Trace: {len(answer.attempts)} attempts")
            for a in answer.attempts:
                status = "✅" if a.validation.ok else f"❌ ({a.validation.stage})"
                print(f"   - Attempt {a.attempt_num}: {status}")
        print()
        continue

    print(f"📊 Retrieved tables: {answer.retrieved_tables[:3]}")
    print(f"🔧 Corrections needed: {answer.n_corrections}")
    print(f"📈 Chart type: {answer.chart_type}")
    print(f"📝 Rows: {len(answer.df)}\n")

    print("SQL:")
    for line in answer.sql.splitlines():
        print(f"  {line}")
    print()

    print("Result preview:")
    print(answer.df.head(3).to_string(index=False))
    print()

    print("Summary:")
    print(f"  {answer.summary}")
    print()