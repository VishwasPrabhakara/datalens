import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from insight import InsightAgent, MAX_RESULT_ROWS


def build_agent(engine):
    agent = InsightAgent.__new__(InsightAgent)
    agent.engine = engine
    return agent


def test_execute_returns_dataframe():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE values_table (value INTEGER)"))
        conn.execute(text("INSERT INTO values_table VALUES (1), (2)"))

    df = build_agent(engine)._execute("SELECT value FROM values_table ORDER BY value")

    assert isinstance(df, pd.DataFrame)
    assert df["value"].tolist() == [1, 2]


def test_execute_rejects_oversized_results():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE values_table (value INTEGER)"))
        conn.execute(
            text(
                "WITH RECURSIVE n(x) AS ("
                "SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x <= :limit"
                ") INSERT INTO values_table SELECT x FROM n"
            ),
            {"limit": MAX_RESULT_ROWS},
        )

    with pytest.raises(ValueError, match="more than"):
        build_agent(engine)._execute("SELECT value FROM values_table")
