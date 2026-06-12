# Security and Data Handling

## Read-only SQL policy

DataLens accepts one parsed SQL query at a time and rejects DML, DDL,
transactions, administrative commands, and multi-statement input. Queries are
validated before execution and result sets are capped at 1,000 rows.

These application checks are not a replacement for database permissions.
Remote databases should use a dedicated read-only account with access limited
to approved schemas and tables.

## LLM data disclosure

Schema metadata and sampled rows are sent to the configured Gemini API to
describe tables and generate SQL. Query results may also be sent to Gemini to
produce a natural-language summary.

Do not connect a database or upload a file containing confidential, regulated,
personal, or otherwise sensitive information unless the relevant data policy
and model-provider terms explicitly allow it.

## Credentials

- Never commit `.env` or Streamlit secrets.
- Use short-lived or restricted database credentials.
- Rotate credentials immediately if they appear in logs, screenshots, issues,
  commits, or exported conversations.

## Reporting

Please report security issues privately to the repository owner rather than
opening a public issue with credentials or sensitive data.
