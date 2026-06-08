"""Smoke test for InsightAgent — runs SQL, picks chart, summarizes."""
from dotenv import load_dotenv
import os

from sqlalchemy import create_engine

from insight import InsightAgent

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

engine = create_engine("sqlite:///chinook.db")
agent = InsightAgent(engine, api_key)

test_cases = [
    # (label, sql, expected_chart_type)
    (
        "Bar — top customers by spending",
        """
        SELECT C.FirstName || ' ' || C.LastName AS Customer,
               SUM(I.Total) AS TotalSpending
        FROM Customer C
        JOIN Invoice I ON C.CustomerId = I.CustomerId
        GROUP BY C.CustomerId
        ORDER BY TotalSpending DESC
        LIMIT 5
        """,
        "bar",
    ),
    (
        "Line — invoices over time",
        """
        SELECT InvoiceDate, SUM(Total) AS DailyTotal
        FROM Invoice
        GROUP BY InvoiceDate
        ORDER BY InvoiceDate
        LIMIT 30
        """,
        "line",
    ),
    (
        "Single value — total revenue",
        "SELECT SUM(Total) AS TotalRevenue FROM Invoice",
        "single_value",
    ),
    (
        "Table — multi-column result",
        "SELECT * FROM Track LIMIT 10",
        "table",
    ),
]

for label, sql, expected in test_cases:
    print(f"\n{'=' * 60}")
    print(f"❓ {label}")
    print(f"{'=' * 60}")
    insight = agent.run(sql, question=label)
    print(f"Chart type:  {insight.chart_type}  (expected: {expected})")
    print(f"Row count:   {insight.row_count}")
    print(f"Columns:     {list(insight.df.columns)}")
    print(f"Chart built: {insight.chart is not None}")
    print(f"\nSummary:")
    print(f"  {insight.summary}")
    print(f"\nFirst 3 rows:")
    print(insight.df.head(3).to_string(index=False))