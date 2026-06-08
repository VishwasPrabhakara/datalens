"""Smoke test for SQLAgent."""
from dotenv import load_dotenv
import os

from schema_profiler import SchemaProfiler
from retrieval import SchemaRetriever
from agents import SQLAgent

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

print("Building profile + retriever for chinook.db...")
profiler = SchemaProfiler("chinook.db")
profiler.profile()
retriever = SchemaRetriever(profiler.documents, api_key)
agent = SQLAgent(api_key)
print(f"Indexed {len(profiler.documents)} tables.\n")

test_queries = [
    "Which 5 artists have the most albums?",
    "Total revenue per country",
    "List the 10 most expensive tracks",
    "How many employees report to each manager?",
    "Find the average song duration by genre",
]

for q in test_queries:
    print(f"❓ {q}")
    docs = retriever.retrieve(q)
    print(f"   Retrieved: {[d.metadata['table_name'] for d in docs]}")
    sql = agent.generate(q, docs)
    print(f"   SQL:")
    for line in sql.splitlines():
        print(f"     {line}")
    print()