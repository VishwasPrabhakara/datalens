# 📊 DataLens — Chat with your database

> Hybrid-retrieval RAG over your database. Ask natural-language questions, get grounded SQL answers with auto-generated charts and self-correcting validation.

**Live Demo:** _(coming after deploy)_

Most "text-to-SQL" tutorials hardcode a schema in a prompt. DataLens reads any database, profiles it on connect, and uses production-grade RAG techniques (hybrid retrieval + multi-agent reasoning + validation loops) to answer questions on databases it has never seen.

---

## 🚀 What makes it different

- **Bring your own database** — Upload SQLite, paste a Postgres/MySQL connection URI, or use the bundled Chinook sample. No hardcoded schemas.
- **Auto-profiling on connect** — Reads tables, infers one-sentence descriptions per table, samples rows. Builds a hybrid index over the schema in seconds.
- **Hybrid schema retrieval** — Combines semantic (FAISS) and keyword (BM25) search over table metadata, fused via Reciprocal Rank Fusion. Catches both meaning and exact terms.
- **5-agent pipeline** — Schema → SQL → Validator → Corrector → Insight. Visible trace shows what happened on each question.
- **Self-correcting validation** — Generated SQL is parsed with `sqlglot` then dry-run with `EXPLAIN` before execution. Validation failures feed back to Gemini for correction (up to 3 retries).
- **Auto-charting** — Result shape determines chart type (bar / line / scatter / single value / table). No LLM call needed for chart picking — pure heuristics.
- **Grounded summaries with units** — Each answer includes a 2-sentence plain-language insight referencing actual values, with proper currency / time / size formatting.

---

## 🏗️ Architecture

![DataLens Architecture](https://github.com/VishwasPrabhakara/datalens/raw/main/architecture.svg)

---

## 🤖 The 5-Agent Pipeline

| Agent | Role |
|-------|------|
| **SchemaProfiler** | Reads DB, samples rows, generates one-sentence descriptions per table (one Gemini call per table) |
| **SchemaRetriever** | Hybrid FAISS + BM25 search over schema metadata. Retrieves top-5 relevant tables per question via RRF fusion |
| **SQLAgent** | Generates SQL using only the retrieved schema. Constrained prompt prevents column hallucination. Has explicit rules to prefer human-readable names over IDs |
| **Validator** | sqlglot dialect-aware syntax check + EXPLAIN dry-run. Catches errors before execution, returns structured error feedback |
| **Corrector** | On validation failure, feeds error back to SQLAgent for correction (max 3 retries) |
| **InsightAgent** | Runs validated SQL, picks chart type heuristically, generates summary with unit-aware formatting ($, seconds, MB) |

---

## 🛠️ Tech Stack

**Core**
- **Python 3.11**
- **Streamlit** — Web UI with chat interface
- **LangChain 0.3** — Pipeline orchestration

**LLM + Embeddings**
- **Gemini 2.5 Flash** — SQL generation, schema descriptions, summaries
- **gemini-embedding-001** — Schema embeddings

**Retrieval + Validation**
- **FAISS** — Vector similarity over schema
- **BM25** — Keyword retrieval over schema
- **sqlglot** — Dialect-aware SQL parsing
- **SQLAlchemy** — Multi-database support (SQLite, Postgres, MySQL)

**Visualization**
- **Plotly Express** — Auto-generated charts
- **pandas** — Data handling

---

## 🏃 Run Locally

### Prerequisites
- Python 3.11+
- Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### Setup

```bash
git clone https://github.com/VishwasPrabhakara/datalens.git
cd datalens

python -m venv venv
.\venv\Scripts\Activate.ps1     # Windows
# source venv/bin/activate       # macOS/Linux

pip install -r requirements.txt

echo "GOOGLE_API_KEY=your_key_here" > .env

streamlit run app.py
```

Open `http://localhost:8501`.

---

## 🌐 Connection Modes

DataLens supports three ways to connect to a database:

| Mode | What it does | Use case |
|------|-------------|----------|
| **Sample (Chinook)** | Uses the bundled Chinook music store SQLite database | Try the app instantly with no setup |
| **Upload SQLite** | Upload your own `.db` / `.sqlite` file | Personal projects, local exports |
| **Connection URI** | Paste a SQLAlchemy URI (Postgres, MySQL, etc.) | Production databases via secure connection string |

---

## 📁 Project Structure

```
datalens/
├── app.py                  # Streamlit UI
├── datalens.py             # Pipeline orchestrator (public API)
├── schema_profiler.py      # Reads DB, builds schema docs with descriptions
├── retrieval.py            # Hybrid FAISS + BM25 retrieval over schema (RRF fusion)
├── agents.py               # SQLAgent (generate + correct)
├── validator.py            # sqlglot + EXPLAIN validation
├── loop.py                 # Generate-validate-correct retry loop
├── insight.py              # InsightAgent (execute + chart + summarize)
├── prompts.py              # Prompt templates
├── chinook.db              # Sample database (bundled)
├── architecture.svg
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## 💡 How It Works

1. **User connects a database** — chooses Chinook sample, uploads SQLite, or pastes a connection URI
2. **SchemaProfiler reads the schema** — for each table, fetches columns + a sample row, calls Gemini once to generate a one-sentence description
3. **Schema documents are indexed** — each table becomes a Document, indexed in FAISS (semantic) and BM25 (keyword) in parallel
4. **User asks a question** — top-5 relevant tables are retrieved via Reciprocal Rank Fusion (RRF) of FAISS and BM25 results
5. **SQLAgent generates SQL** — constrained to use only the retrieved schema. Explicit rules prefer human-readable names over foreign-key IDs
6. **Validator checks it** — sqlglot parses for syntax, EXPLAIN dry-runs against the live DB to catch missing columns/tables
7. **If validation fails, Corrector kicks in** — the error is fed back to the SQLAgent with the original question and schema, up to 3 retries
8. **InsightAgent executes** — runs the validated SQL, picks a chart type heuristically based on result shape, generates a 2-sentence summary with unit-aware formatting
9. **UI renders** — summary → chart → expandable SQL → expandable trace (only shown if corrections happened) → expandable full data

---

## 🧠 Sample Questions

Try these on the Chinook sample database:

- "Which 5 customers spent the most?"
- "What's the total revenue per genre?"
- "Show me invoice totals by month"
- "Which artist has the most tracks?"
- "Average track duration by genre"
- "List the top 10 most expensive tracks"
- "How many employees report to each manager?"

---

## 📝 Built By

**Vishwas Prabhakara** — ML Engineer @ IISc

[GitHub](https://github.com/VishwasPrabhakara) · [LinkedIn](https://www.linkedin.com/in/vishwas-prabhakara-2050821b6/) · [PaperLens](https://github.com/VishwasPrabhakara/Chat_with_PDF) (related project: same architecture pattern applied to PDFs)

---

## 📄 License

MIT