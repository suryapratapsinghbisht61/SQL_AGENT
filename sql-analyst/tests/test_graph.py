import pytest

from app import graph


@pytest.fixture
def fake_deps(monkeypatch):
    """Replace the LLM and the database; the real validator static checks still run."""
    prompts = []
    executed = []
    monkeypatch.setattr(graph.db, "get_schema_text", lambda: "artist(artist_id INTEGER PK, name VARCHAR)")
    monkeypatch.setattr(graph.db, "explain", lambda sql: None)

    def run_query(sql):
        executed.append(sql)
        return ["name"], [{"name": "AC/DC"}]

    monkeypatch.setattr(graph.db, "run_query", run_query)

    def use(responses):
        it = iter(responses)

        def call_llm(prompt):
            prompts.append(prompt)
            return next(it)

        monkeypatch.setattr(graph, "call_llm", call_llm)

    return use, prompts, executed


def test_strip_fences():
    assert graph.strip_fences("```sql\nSELECT 1;\n```") == "SELECT 1"


def test_retry_after_bad_query(fake_deps):
    use, prompts, executed = fake_deps
    use(["DELETE FROM artist", "```sql\nSELECT name FROM artist LIMIT 1\n```", "The first artist is AC/DC."])
    out = graph.build_graph().invoke({"question": "Name one artist"})
    assert out["attempts"] == 2
    assert out["error"] is None
    assert out["sql"] == "SELECT name FROM artist LIMIT 1"
    assert executed == ["SELECT name FROM artist LIMIT 1"]
    assert "DELETE FROM artist" in prompts[1] and "Only SELECT" in prompts[1]  # error fed back
    assert out["answer"] == "The first artist is AC/DC."


def test_graceful_failure_after_max_attempts(fake_deps):
    use, prompts, executed = fake_deps
    use(["DROP TABLE artist"] * 10)
    out = graph.build_graph().invoke({"question": "Delete everything"})
    assert out["attempts"] == 3
    assert len(prompts) == 3  # no explain call
    assert executed == []
    assert out["answer"].startswith("I couldn't produce a valid query for this question")
    assert "Only SELECT" in out["answer"]


def test_execute_error_routes_back(fake_deps, monkeypatch):
    use, prompts, _ = fake_deps
    results = iter([RuntimeError("canceling statement due to statement timeout"), (["n"], [{"n": 1}])])

    def run_query(sql):
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(graph.db, "run_query", run_query)
    use(["SELECT 1", "SELECT 2", "One."])
    out = graph.build_graph().invoke({"question": "q"})
    assert out["attempts"] == 2 and "statement timeout" in prompts[1]


def test_zero_rows(fake_deps, monkeypatch):
    use, prompts, _ = fake_deps
    monkeypatch.setattr(graph.db, "run_query", lambda sql: (["name"], []))
    use(["SELECT name FROM artist WHERE false"])
    out = graph.build_graph().invoke({"question": "q"})
    assert "returned no rows" in out["answer"]
    assert len(prompts) == 1
