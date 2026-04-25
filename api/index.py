import json
import os
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

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


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing {name}")
    return value


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "hasOpenAI": bool(os.getenv("OPENAI_API_KEY")),
        "hasGoogle": bool(os.getenv("GOOGLE_API_KEY")),
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
