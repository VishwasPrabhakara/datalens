"""Smoke test for Validator — both pass and fail cases."""
from sqlalchemy import create_engine

from validator import Validator

engine = create_engine("sqlite:///chinook.db")
validator = Validator(engine, dialect="sqlite")

test_cases = [
    # (label, sql, should_pass)
    ("Valid simple query",
     "SELECT * FROM Artist LIMIT 5",
     True),
    ("Valid join with aggregation",
     "SELECT ar.Name, COUNT(al.AlbumId) AS n FROM Artist ar JOIN Album al ON ar.ArtistId = al.ArtistId GROUP BY ar.Name",
     True),
    ("Syntax error — typo in keyword",
     "SELCT * FROM Artist",
     False),
    ("Semantic error — missing column",
     "SELECT NonExistentColumn FROM Artist",
     False),
    ("Semantic error — missing table",
     "SELECT * FROM TableThatDoesNotExist",
     False),
    ("Semantic error — bad join column",
     "SELECT * FROM Artist a JOIN Album b ON a.BadCol = b.ArtistId",
     False),
]

print("Running validator tests...\n")
passed = 0
for label, sql, expected_ok in test_cases:
    result = validator.validate(sql)
    actual_ok = result.ok
    match = (actual_ok == expected_ok)
    icon = "✅" if match else "❌"
    print(f"{icon} {label}")
    print(f"   Expected: {'ok' if expected_ok else 'fail'}, Got: {'ok' if actual_ok else 'fail'}")
    if not result.ok:
        print(f"   Error ({result.stage}): {result.error}")
    print()
    if match:
        passed += 1

print(f"{'=' * 50}")
print(f"Result: {passed}/{len(test_cases)} tests passed")