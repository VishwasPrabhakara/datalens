"""Smoke test for SchemaRetriever."""
from dotenv import load_dotenv
import os

from schema_profiler import SchemaProfiler
from retrieval import SchemaRetriever

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

print("Building profile + retriever for chinook.db...")
profiler = SchemaProfiler("chinook.db")
profiler.profile()
retriever = SchemaRetriever(profiler.documents, api_key)
print(f"Indexed {len(profiler.documents)} tables.\n")

# Run a few representative queries
test_queries = [
    "Which artists have the most albums?",
    "List all employees and their managers",
    "What's the total revenue from invoices?",
    "Find all jazz tracks under 5 minutes",
    "Which playlists contain rock songs?",
]

for q in test_queries:
    print(f"❓ {q}")
    results = retriever.retrieve(q)
    for i, doc in enumerate(results, 1):
        print(f"   [{i}] {doc.metadata['table_name']}")
    print()