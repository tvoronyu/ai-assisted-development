from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.classify import router as classify_router
from src.api.import_ import router as import_router
from src.api.tickets import router as tickets_router
from src.db.session import engine
from src.logging_config import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield
    await engine.dispose()


app = FastAPI(
    title="Customer Support Ticket System",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(tickets_router)
app.include_router(import_router)
app.include_router(classify_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
