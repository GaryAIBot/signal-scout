# Signal Scout

A tiny full-stack Vercel app with a static front-end and FastAPI backend.
It uses Google web search for grounding and OpenAI for turning findings into a practical action brief.

## Env vars

Server-side:
- OPENAI_API_KEY
- GOOGLE_API_KEY

## Local dev

```bash
source /home/ubuntu/.config/gary/vercel-secrets.env
uvicorn api.index:app --reload
```
