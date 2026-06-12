"""Smoke test for SchemaProfiler."""
# Manual integration check; requires Gemini API access.
from dotenv import load_dotenv
from schema_profiler import SchemaProfiler

load_dotenv()

print("Profiling chinook.db... (this calls Gemini once per table — ~10-15 seconds total)")
profiler = SchemaProfiler("chinook.db")
profiler.profile()

print(f"\nProfiled {len(profiler.profiles)} tables.\n")

for profile in profiler.profiles:
    print(f"📋 {profile.name}")
    print(f"   {profile.description}")
    print(f"   Columns: {len(profile.columns)} — {', '.join(c for c, _ in profile.columns[:5])}{'...' if len(profile.columns) > 5 else ''}")
    print()

print("=" * 60)
print("Sample Document (first table):")
print("=" * 60)
print(profiler.documents[0].page_content)
print()
print("Metadata:", profiler.documents[0].metadata)
