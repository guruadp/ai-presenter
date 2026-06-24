import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import knowledge_bases, orchestrator, projects, qa, retrieval, robot


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    settings = get_settings()
    for path in (
        settings.STORAGE_DIR,
        settings.CHROMA_DIR,
        os.path.dirname(settings.DATABASE_URL.replace("sqlite:///", "")),
    ):
        if path:
            os.makedirs(path, exist_ok=True)
    logging.basicConfig(level=settings.LOG_LEVEL)
    init_db()

    if settings.ROBOT_ENABLED:
        from app.services.robot_bridge import RobotBridge
        app.state.robot_bridge = RobotBridge(
            interface=settings.ROBOT_NETWORK_INTERFACE,
            volume=settings.ROBOT_VOLUME,
            gain=settings.ROBOT_PCM_GAIN,
        )
    else:
        app.state.robot_bridge = None

    yield

    if app.state.robot_bridge:
        await app.state.robot_bridge.detach()


app = FastAPI(title="Ednex AI Presenter", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge_bases.router)
app.include_router(projects.router)
app.include_router(qa.router)
app.include_router(retrieval.router)
app.include_router(orchestrator.router)
app.include_router(robot.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ednex-ai-presenter"}
