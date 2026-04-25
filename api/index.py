import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

app = FastAPI(title="Signal Scout")

GOOGLE_SEARCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
SYSTEM_PROMPT = """You turn grounded search findings into a concise execution brief.
Return valid JSON with keys:
summary: string,
angle: string,
tasks: array of 3 to 6 short actionable strings,
risks: array of 2 to 4 short strings,
questions: array of 2 to 4 short strings.
Keep it crisp and practical.
"""


class Base(DeclarativeBase):
    pass


class SavedScout(Base):
    __tablename__ = "saved_scouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(Text())
    summary: Mapped[str] = mapped_column(Text())
    angle: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SaveScoutPayload(BaseModel):
    query: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1)
    angle: str = Field(..., min_length=1)


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing {name}")
    return value


def get_session_factory():
    database_url = get_required_env("DATABASE_URL")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@app.on_event("startup")
async def startup() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    session_factory, engine = get_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "hasOpenAI": bool(os.getenv("OPENAI_API_KEY")),
        "hasGoogle": bool(os.getenv("GOOGLE_API_KEY")),
        "hasDatabase": bool(os.getenv("DATABASE_URL")),
    }


@app.get("/api/demo")
async def demo() -> Dict[str, Any]:
    return await run_workflow("What new AI workflow ideas should a solo builder try for tiny Vercel apps this month?")


@app.get("/api/scout")
async def scout(query: str) -> Dict[str, Any]:
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    return await run_workflow(query)


@app.get("/api/saved-scouts")
async def list_saved_scouts() -> Dict[str, Any]:
    session_factory, engine = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(SavedScout).order_by(SavedScout.created_at.desc()).limit(20))
        items = result.scalars().all()
    await engine.dispose()
    return {
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "query": item.query,
                "summary": item.summary,
                "angle": item.angle,
                "createdAt": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]
    }


@app.post("/api/saved-scouts")
async def save_scout(payload: SaveScoutPayload) -> Dict[str, Any]:
    session_factory, engine = get_session_factory()
    record = SavedScout(
        id=str(uuid4()),
        title=payload.title.strip(),
        query=payload.query.strip(),
        summary=payload.summary.strip(),
        angle=payload.angle.strip(),
        created_at=datetime.now(timezone.utc),
    )
    async with session_factory() as session:
        session.add(record)
        await session.commit()
    await engine.dispose()
    return {
        "ok": True,
        "item": {
            "id": record.id,
            "title": record.title,
            "query": record.query,
            "summary": record.summary,
            "angle": record.angle,
            "createdAt": record.created_at.isoformat(),
        },
    }


async def run_workflow(query: str) -> Dict[str, Any]:
    google_key = get_required_env("GOOGLE_API_KEY")
    openai_key = get_required_env("OPENAI_API_KEY")
    search = await google_grounded_search(query, google_key)
    brief = await openai_brief(query, search, openai_key)
    return {"query": query, "search": search, "brief": brief}


async def google_grounded_search(query: str, api_key: str) -> Dict[str, Any]:
    payload = {
        "tools": [{"google_search": {}}],
        "contents": [{"parts": [{"text": f"Search the web and summarize useful recent findings for: {query}"}]}],
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{GOOGLE_SEARCH_URL}?key={api_key}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Google search failed: {response.text[:400]}")
    data = response.json()
    return {
        "summary": extract_gemini_text(data),
        "sources": extract_gemini_sources(data)[:8],
    }


async def openai_brief(query: str, search: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    source_lines = "\n".join(f"- {item.get('title', 'Untitled')}: {item.get('url', '')}" for item in search.get("sources", []))
    payload = {
        "model": "gpt-4.1-mini",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "signal_scout_brief",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "angle": {"type": "string"},
                        "tasks": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "questions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "angle", "tasks", "risks", "questions"],
                },
            }
        },
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Query: {query}\n\nSearch summary:\n{search.get('summary', '')}\n\nSources:\n{source_lines}\n\nReturn JSON only.",
            },
        ],
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenAI call failed: {response.text[:400]}")
    data = response.json()
    text = extract_openai_text(data)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "summary": text,
            "angle": "Model returned plain text instead of strict JSON.",
            "tasks": [],
            "risks": ["Response formatting fallback triggered"],
            "questions": [],
        }


def extract_gemini_text(data: Dict[str, Any]) -> str:
    texts: List[str] = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def extract_gemini_sources(data: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for candidate in data.get("candidates", []):
        meta = candidate.get("groundingMetadata", {})
        for chunk in meta.get("groundingChunks", []):
            web = chunk.get("web") or {}
            url = web.get("uri")
            title = web.get("title")
            if url and url not in seen:
                out.append({"title": title or url, "url": url})
                seen.add(url)
    return out


def extract_openai_text(data: Dict[str, Any]) -> str:
    parts: List[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "\n".join(parts).strip() or data.get("output_text", "").strip()


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})
