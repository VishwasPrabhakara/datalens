"""
DataLens — Streamlit UI.

Chat-with-your-database with hybrid schema retrieval, multi-agent SQL
generation, self-correcting validation, and auto-charting.
"""
from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from datalens import Answer, DataLens

load_dotenv()

st.set_page_config(
    page_title="DataLens — Chat with your database",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "lens" not in st.session_state:
    st.session_state.lens = None
if "messages" not in st.session_state:
    st.session_state.messages = []  # list[{role, content, answer?}]
if "db_label" not in st.session_state:
    st.session_state.db_label = ""
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


def _api_key() -> str | None:
    try:
        return st.secrets["GOOGLE_API_KEY"]
    except (FileNotFoundError, KeyError):
        return os.getenv("GOOGLE_API_KEY")


def _markdown_export() -> str:
    lines = [
        "# DataLens conversation",
        f"_Exported {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        f"**Database:** {st.session_state.db_label or '(not connected)'}",
        "",
        "---",
        "",
    ]
    for m in st.session_state.messages:
        if m["role"] == "user":
            lines.append(f"### 🧑 {m['content']}\n")
        else:
            ans: Answer | None = m.get("answer")
            if ans and ans.ok:
                lines.append(f"**Summary:** {ans.summary}\n")
                lines.append("```sql")
                lines.append(ans.sql)
                lines.append("```\n")
                if ans.df is not None and not ans.df.empty:
                    lines.append("First rows:\n")
                    lines.append("```")
                    lines.append(ans.df.head(10).to_string(index=False))
                    lines.append("```\n")
            elif ans:
                lines.append(f"⚠️ {ans.error}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sidebar — connect, summaries, stats, export
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 📊 DataLens")
    st.caption(
        "Hybrid schema retrieval · multi-agent SQL · self-correcting validation · auto-charting."
    )
    st.divider()

    api_key = _api_key()
    if not api_key:
        st.error(
            "GOOGLE_API_KEY not set. Add it to `.env` (local) or "
            "`.streamlit/secrets.toml` (deployed)."
        )

    st.markdown("**🗄️ Choose a database**")
    db_choice = st.radio(
        "Source",
        ["Sample (Chinook)", "Upload SQLite", "Connection URI"],
        label_visibility="collapsed",
    )

    db_uri: str | None = None
    db_label: str = ""

    if db_choice == "Sample (Chinook)":
        if os.path.exists("chinook.db"):
            db_uri = "chinook.db"
            db_label = "Chinook (sample)"
            st.caption("Using the bundled Chinook music store database.")
        else:
            st.error("chinook.db not found in project root.")

    elif db_choice == "Upload SQLite":
        uploaded = st.file_uploader("Upload .db file", type=["db", "sqlite", "sqlite3"])
        if uploaded is not None:
            tmp_path = os.path.join(tempfile.gettempdir(), uploaded.name)
            with open(tmp_path, "wb") as f:
                f.write(uploaded.getvalue())
            db_uri = tmp_path
            db_label = uploaded.name

    else:  # Connection URI
        db_uri_input = st.text_input(
            "SQLAlchemy URI",
            placeholder="postgresql+psycopg2://user:pass@host:5432/dbname",
            type="password",
        )
        if db_uri_input:
            db_uri = db_uri_input
            db_label = db_uri_input.split("@")[-1] if "@" in db_uri_input else db_uri_input

    if st.button(
        "Connect",
        type="primary",
        use_container_width=True,
        disabled=not db_uri or not api_key,
    ):
        with st.spinner("Profiling schema and building retriever…"):
            try:
                lens = DataLens(db_uri, api_key=api_key)
                lens.connect()
                st.session_state.lens = lens
                st.session_state.db_label = db_label
                st.session_state.messages = []
                st.success(f"Connected. {lens.table_count} tables indexed.")
            except Exception as e:
                st.error(f"Failed to connect: {e}")

    if st.session_state.lens:
        lens: DataLens = st.session_state.lens

        st.divider()
        st.markdown("**📚 Tables**")
        for name, desc in lens.table_summaries.items():
            with st.expander(name, expanded=False):
                st.write(desc)

        st.divider()
        st.markdown("**📊 Session stats**")
        n_questions = sum(1 for m in st.session_state.messages if m["role"] == "user")
        n_corrections = sum(
            m["answer"].n_corrections
            for m in st.session_state.messages
            if m.get("answer") is not None
        )
        cols = st.columns(2)
        cols[0].metric("Questions", n_questions)
        cols[1].metric("Corrections", n_corrections)

        st.divider()
        st.download_button(
            "⬇️ Export chat (Markdown)",
            data=_markdown_export(),
            file_name="datalens_conversation.md",
            mime="text/markdown",
            use_container_width=True,
            disabled=not st.session_state.messages,
        )
        if st.button("🗑️ Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ---------------------------------------------------------------------------
# Answer renderer
# ---------------------------------------------------------------------------
# Common column-name hints → display formatters
def _format_value(col_name: str, value) -> str:
    """Apply unit/format hints based on column name. Best-effort, not a hard rule."""
    if value is None:
        return "—"
    lower = str(col_name).lower()
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if any(k in lower for k in ["revenue", "total", "spending", "price", "amount", "cost", "sales"]):
        return f"${num:,.2f}"
    if "millisecond" in lower:
        seconds = num / 1000
        return f"{seconds:,.1f}s"
    if "byte" in lower:
        mb = num / (1024 * 1024)
        return f"{mb:,.2f} MB"
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.2f}"


def render_answer(ans: Answer, idx: int) -> None:
    """Render a full Answer: summary, chart, SQL, trace, rows."""
    if not ans.ok:
        st.error(ans.error or "Sorry, I couldn't answer that.")
        if ans.attempts:
            with st.expander(f"🔧 Trace — {len(ans.attempts)} attempts"):
                for a in ans.attempts:
                    status = "✅" if a.validation.ok else f"❌ ({a.validation.stage})"
                    st.markdown(f"**Attempt {a.attempt_num}** — {status}")
                    if not a.validation.ok:
                        st.code(a.validation.error, language="text")
                    st.code(a.sql, language="sql")
        return

    
    # Summary — escape $ so Streamlit doesn't interpret them as LaTeX math delimiters
    st.markdown(ans.summary.replace("$", r"\$"))

    # Chart or single value
    if ans.chart_type == "single_value" and ans.df is not None and not ans.df.empty:
        col_name = ans.df.columns[0]
        raw_value = ans.df.iloc[0, 0]
        st.metric(label=col_name, value=_format_value(col_name, raw_value))
    elif ans.chart is not None:
        st.plotly_chart(
            ans.chart,
            use_container_width=True,
            key=f"chart_{idx}_{id(ans)}",
            theme="streamlit",
        )

    # Stats badges
    badges = []
    if ans.retrieved_tables:
        badges.append(f"📊 {', '.join(ans.retrieved_tables[:3])}")
    if ans.n_corrections:
        badges.append(f"🔧 {ans.n_corrections} correction(s)")
    if ans.df is not None:
        badges.append(f"📝 {len(ans.df)} row(s)")
    if badges:
        st.caption(" · ".join(badges))

    # SQL
    with st.expander("🧠 Generated SQL"):
        st.code(ans.sql or "", language="sql")

    # Full data
    if ans.df is not None and not ans.df.empty:
        with st.expander(f"📑 Full data ({len(ans.df)} rows)"):
            st.dataframe(ans.df, use_container_width=True)

    # Trace (only show if there were corrections)
    if ans.n_corrections > 0:
        with st.expander(f"🔧 Correction trace — {len(ans.attempts)} attempts"):
            for a in ans.attempts:
                status = "✅" if a.validation.ok else f"❌ ({a.validation.stage})"
                st.markdown(f"**Attempt {a.attempt_num}** — {status}")
                if not a.validation.ok:
                    st.code(a.validation.error, language="text")
                st.code(a.sql, language="sql")


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

st.markdown("## 📊 DataLens")
st.caption(
    "Ask grounded, cited questions about your database. "
    "Hybrid schema retrieval → multi-agent SQL → self-correcting validation → auto-charts."
)

if st.session_state.lens is None:
    st.info("👈 Choose a database in the sidebar and click **Connect** to begin.")
    sample_questions = [
        "Which 5 customers spent the most?",
        "What's the total revenue per genre?",
        "Show me invoice totals by month",
        "Which artist has the most tracks?",
    ]
    st.markdown("**Try a question once connected:**")
    for q in sample_questions:
        st.markdown(f"- *{q}*")
    st.stop()

# Render past messages
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            ans: Answer | None = msg.get("answer")
            if ans:
                render_answer(ans, idx=i)
            else:
                st.markdown(msg["content"])

# Pending or new question
prompt = st.session_state.pending_question
st.session_state.pending_question = None
if not prompt:
    prompt = st.chat_input("Ask a question about your data…")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving · generating · validating · executing…"):
            answer = st.session_state.lens.ask(prompt)
        render_answer(answer, idx=len(st.session_state.messages))

    st.session_state.messages.append(
        {"role": "assistant", "content": answer.summary or answer.error, "answer": answer}
    )