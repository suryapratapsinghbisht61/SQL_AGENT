# SQL Analyst Agent

Ask a question in plain English. The agent writes a PostgreSQL query, checks that it is safe, runs it against the Chinook sample database, and explains the result.

Built with LangGraph, FastAPI, SQLAlchemy, sqlglot and Gemini (free tier).

```
get_schema -> generate_sql -> validate -> execute -> explain -> END
                  ^              |           |
                  +-- retry -----+-----------+   (max 3 attempts, then a graceful failure)
```

## Setup

1. Get a free API key from Google AI Studio: https://aistudio.google.com/apikey
2. Copy the env file and fill it in:
   ```bash
   cp .env.example .env
   # set GOOGLE_API_KEY, and change both passwords
   ```
   `DATABASE_URL` must use the read-only role (`RO_USER` / `RO_PASSWORD`), not the admin user.
3. Start Postgres. On first start it loads Chinook and creates the read-only role:
   ```bash
   docker compose up -d
   ```
   The init scripts only run on an empty volume. If you change `RO_PASSWORD` later, run `docker compose down -v` and start again.
4. Install dependencies (Python 3.11):
   ```bash
   python3.11 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
5. Run the API:
   ```bash
   uvicorn app.main:app --reload
   ```

## Usage

Open http://localhost:8000 for the chat page, or use the API directly:

```bash
curl localhost:8000/health

curl -s localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Which 5 artists have the most tracks?"}'

curl -s localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "What were total sales per country? Top 5 only."}'

curl -s localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Which employee supports the most customers?"}'

curl -s localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Which genre has the longest average track length?"}'
```

Response:

```json
{"answer": "...", "sql": "SELECT ...", "rows": [...], "attempts": 1, "error": null}
```

`question` must be 1–500 characters, or the API returns 422. If Gemini is still rate limited after retries, `/ask` returns 503 with a JSON `detail`.

## Tests

```bash
pytest
```

The tests never call Gemini: the LLM is mocked everywhere, and a fixture fails any test that reaches the real client. Validator and DB tests use the docker Postgres and are skipped if it is not running.

## Safety design

The model writes SQL, so the SQL is treated as untrusted. Four independent layers:

1. **Read-only role.** The app connects as a role that has only `CONNECT`, `USAGE` and `SELECT`. It cannot write or create anything, even if every other check fails.
2. **Validator** (`app/validator.py`). sqlglot parses the query. Exactly one statement is allowed, and it must be a `SELECT` (CTEs and `UNION` are fine). Any write or DDL node anywhere in the tree is rejected, including data-modifying CTEs and `SELECT INTO`. Dangerous functions are blocked: `pg_*` (such as `pg_sleep` and `pg_read_file`), `lo_*`, `dblink`, `set_config`, and others. Then `EXPLAIN` is run to check that the tables and columns exist.
3. **Timeout.** Each statement runs in a read-only transaction with `statement_timeout` (default 10 s).
4. **Row limit.** A server-side cursor fetches at most `ROW_LIMIT` rows (default 100). Up to 20 of those rows are sent to the LLM for the explanation.

If no valid query is produced in `MAX_ATTEMPTS` (3), the agent answers "I couldn't produce a valid query for this question" and gives the last error. It never guesses an answer.

## Gemini free tier

- **Rate limits.** The free tier allows only a few requests per minute and a daily cap, and the limits vary by model. One question uses 2 LLM calls (more if a query has to be retried). `call_llm()` waits at least `MIN_SECONDS_BETWEEN_LLM_CALLS` (default 6) between calls. On a 429 / `RESOURCE_EXHAUSTED` it retries with exponential backoff, up to 3 tries.
- **Changing the model.** Set `GEMINI_MODEL` in `.env` (default `gemini-3.8-flash`), for example `GEMINI_MODEL=gemini-3.5-flash-lite`. To switch providers, edit only `get_llm()` in `app/llm.py`.
- **Privacy.** Google may use free-tier inputs and outputs to improve its models. Your question, the database schema and up to 20 result rows are sent to Gemini. Use only sample or non-sensitive data.
