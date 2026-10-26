"""FastAPI app exposing the SQL analyst agent."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, StringConstraints

from app.graph import build_graph
from app.llm import LLMError

log = logging.getLogger("sql_analyst")
STATIC_DIR = Path(__file__).parent / "static"


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AskResponse(BaseModel):
    answer: str
    sql: str
    rows: list[dict[str, Any]]
    attempts: int
    error: str | None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = build_graph()
    yield


app = FastAPI(title="SQL Analyst Agent", lifespan=lifespan)


@app.exception_handler(LLMError)
async def llm_error(request: Request, exc: LLMError) -> JSONResponse:
    log.warning("LLM error: %s", exc)
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/", include_in_schema=False)
def chat_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request) -> AskResponse:
    # Sync endpoint: FastAPI runs it in a threadpool, so slow LLM calls don't block the loop.
    out = request.app.state.graph.invoke({"question": body.question})
    return AskResponse(
        answer=out["answer"],
        sql=out.get("sql", ""),
        rows=out.get("rows", []),
        attempts=out.get("attempts", 0),
        error=out.get("error"),
    )
