import sqlite3

con = sqlite3.connect('chinook.db')
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

print(f'Found {len(tables)} tables:')
for t in tables:
    print(f'  - {t}')