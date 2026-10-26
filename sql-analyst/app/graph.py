"""LangGraph agent: question -> SQL -> validate -> execute -> plain-English answer."""
import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app import db, validator
from app.config import settings
from app.llm import call_llm

EXPLAIN_ROWS = 20


class State(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    error: str | None
    rows: list[dict[str, Any]]
    columns: list[str]
    attempts: int
    answer: str


def strip_fences(text: str) -> str:
    """Remove markdown code fences and a trailing semicolon from model output."""
    text = re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", text.strip())
    return text.strip().rstrip(";").strip()


def get_schema(state: State) -> State:
    return {"schema": db.get_schema_text(), "attempts": 0, "error": None}


def generate_sql(state: State) -> State:
    prompt = (
        "You write PostgreSQL queries for this database schema:\n"
        f"{state['schema']}\n\n"
        f"Question: {state['question']}\n"
    )
    if state.get("error"):
        prompt += (
            f"\nYour previous query:\n{state['sql']}\n"
            f"failed with this error:\n{state['error']}\nFix it.\n"
        )
    prompt += (
        "\nReturn ONLY a single PostgreSQL SELECT query. "
        "No markdown, no code fences, no explanation."
    )
    return {"sql": strip_fences(call_llm(prompt)), "attempts": state["attempts"] + 1}


def validate(state: State) -> State:
    return {"error": validator.validate_sql(state["sql"])}


def execute(state: State) -> State:
    try:
        columns, rows = db.run_query(state["sql"])
    except Exception as e:  # any DB error goes back to the model to fix
        return {"error": f"Query failed: {str(getattr(e, 'orig', e)).strip().splitlines()[0]}"}
    return {"columns": columns, "rows": rows, "error": None}


def explain(state: State) -> State:
    rows = state["rows"]
    if not rows:
        return {"answer": "The query ran successfully but returned no rows, so there is no matching data."}
    shown = rows[:EXPLAIN_ROWS]
    prompt = (
        f"Question: {state['question']}\n"
        f"SQL that was run:\n{state['sql']}\n"
        f"Result: {len(rows)} row(s); the first {len(shown)} are below as JSON.\n"
        f"{json.dumps(shown, default=str)}\n\n"
        "Answer the question in short plain English using ONLY these rows. "
        "Do not invent or estimate anything that is not in the rows. "
        "If the rows shown are not the full result, say so."
    )
    return {"answer": call_llm(prompt).strip()}


def fail(state: State) -> State:
    return {
        "answer": f"I couldn't produce a valid query for this question. Last error: {state['error']}",
        "rows": [],
    }


def _after_check(state: State) -> str:
    if state.get("error") is None:
        return "ok"
    return "fail" if state["attempts"] >= settings.max_attempts else "retry"


def build_graph():
    """Compile the agent graph."""
    g = StateGraph(State)
    for name, fn in [("get_schema", get_schema), ("generate_sql", generate_sql), ("validate", validate),
                     ("execute", execute), ("explain", explain), ("fail", fail)]:
        g.add_node(name, fn)
    g.set_entry_point("get_schema")
    g.add_edge("get_schema", "generate_sql")
    g.add_edge("generate_sql", "validate")
    g.add_conditional_edges("validate", _after_check, {"ok": "execute", "retry": "generate_sql", "fail": "fail"})
    g.add_conditional_edges("execute", _after_check, {"ok": "explain", "retry": "generate_sql", "fail": "fail"})
    g.add_edge("explain", END)
    g.add_edge("fail", END)
    return g.compile()
