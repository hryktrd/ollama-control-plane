from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import agents, jobs, openai, anthropic, admin
from db.base import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Ollama Control Plane", lifespan=lifespan)

app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(openai.router, prefix="/v1", tags=["openai"])
app.include_router(anthropic.router, prefix="/v1", tags=["anthropic"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
