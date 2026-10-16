"""FastAPI application for HF Agent web interface."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextvars import ContextVar
import json
import uuid
import traceback
import re
from config import get_settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

def mask_sensitive_data(text: str) -> str:
    if not text:
        return text
    # Mask MongoDB URIs
    text = re.sub(r'mongodb(?:\+srv)?://([^:]+):([^@]+)@', r'mongodb+srv://***:***@', text)
    # Mask Bearer tokens/JWTs
    text = re.sub(r'ey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', r'[REDACTED_JWT]', text)
    # Mask standard API Keys
    text = re.sub(r'(?:sk-[A-Za-z0-9-_]+|AQ\.[A-Za-z0-9_-]+|\b[A-Za-z0-9]{32}\b)', r'[REDACTED_KEY]', text)
    return text

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get("-"),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        
        # Serialize and mask
        raw_json = json.dumps(log_record)
        return mask_sensitive_data(raw_json)

# Settings are loaded here once, which internally loads .env
settings = get_settings()

from routes.agent import router as agent_router  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from session_manager import session_manager  # noqa: E402

# Configure logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, settings.LOG_LEVEL))
for handler in logger.handlers:
    logger.removeHandler(handler)
log_handler = logging.StreamHandler()
log_handler.setFormatter(JsonFormatter())
logger.addHandler(log_handler)

app_logger = logging.getLogger(__name__)
SHUTDOWN_USAGE_REFRESH_CONCURRENCY = 32
TOKEN_HEALTH_CHECK_INTERVAL_S = settings.TOKEN_HEALTH_INTERVAL_S


async def _token_health_monitor() -> None:
    """C3: Background task — probes all direct-provider tokens periodically.

    Unhealthy tokens (rate-limited or auth-failed) receive a cooldown in the
    pool so subsequent calls automatically rotate to a healthy key.
    Runs until the server shuts down.
    """
    from agent.core.token_pool import token_pool

    logger.info(
        "Token health monitor started (interval=%ds)", TOKEN_HEALTH_CHECK_INTERVAL_S
    )
    while True:
        await asyncio.sleep(TOKEN_HEALTH_CHECK_INTERVAL_S)
        try:
            await token_pool.probe_all_tokens()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Token health probe cycle failed: %s", e)


async def _flush_session_on_shutdown(sid: str, agent_session, semaphore) -> None:
    sess = agent_session.session
    if not sess.config.save_sessions:
        return
    try:
        async with semaphore:
            await session_manager.refresh_session_usage_metrics(
                agent_session,
                error_code="lifespan_billing_snapshot_error",
            )
            sess.save_and_upload_detached(sess.config.session_dataset_repo)
            logger.info("Flushed session %s on shutdown", sid)
    except Exception as e:
        logger.warning("Failed to flush session %s: %s", sid, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    await session_manager.start()

    # Initialize token pool
    from agent.core.token_pool import token_pool
    store = getattr(session_manager, 'persistence_store', None)
    db_client = getattr(store, 'client', None)
    await token_pool.initialize(db_client=db_client)

    # Initialize auth handler (SQLite persistence — no MongoDB required)
    from auth_local import auth_handler
    auth_handler.initialize(db_client)  # db_client may be None — that's fine

    # C3: Start the background token health monitor
    health_monitor_task = asyncio.create_task(
        _token_health_monitor(), name="token_health_monitor"
    )

    # Start in-process hourly KPI rollup. Replaces an external cron so the
    # rollup lives next to the data and reuses the Space's HF token.
    try:
        import kpis_scheduler

        kpis_scheduler.start()
    except Exception as e:
        logger.warning("KPI scheduler failed to start: %s", e)
    yield

    logger.info("Shutting down HF Agent backend...")
    # Cancel the health monitor on shutdown
    health_monitor_task.cancel()
    try:
        await health_monitor_task
    except asyncio.CancelledError:
        pass
    try:
        import kpis_scheduler

        await kpis_scheduler.shutdown()
    except Exception as e:
        logger.warning("KPI scheduler shutdown failed: %s", e)

    # Final-flush: save every still-active session so we don't lose traces on
    # server restart. Billing refreshes are timeboxed and bounded; uploads are
    # detached subprocesses.
    try:
        semaphore = asyncio.Semaphore(SHUTDOWN_USAGE_REFRESH_CONCURRENCY)
        await asyncio.gather(
            *(
                _flush_session_on_shutdown(sid, agent_session, semaphore)
                for sid, agent_session in list(session_manager.sessions.items())
            )
        )
    except Exception as e:
        logger.warning("Lifespan final-flush skipped: %s", e)
    await session_manager.close()


# Disable FastAPI auto-docs when running on HF Spaces (SPACE_ID is set by the
# platform) to avoid exposing the full API surface to anonymous visitors. Local
# dev keeps /docs and /redoc available.
_DOCS_DISABLED = settings.SPACE_ID is not None

app = FastAPI(
    title="HF Agent",
    description="ML Engineering Assistant API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _DOCS_DISABLED else "/docs",
    redoc_url=None if _DOCS_DISABLED else "/redoc",
    openapi_url=None if _DOCS_DISABLED else "/openapi.json",
)

@app.get("/test-logging")
async def test_logging(request: Request):
    logger.info("Request tracing test")
    return {"message": "Logging test successful"}

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health/live", tags=["health"])
async def liveness_probe():
    """Fast liveness check bypassing middlewares."""
    return {"status": "alive"}

@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    # Liveness probe should be fast and bypass logic
    if request.url.path == "/health/live":
        return await call_next(request)
        
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_var.set(req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        request_id_var.reset(token)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    app_logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "request_id": request_id_var.get("-")},
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id_var.get("-")},
        headers=getattr(exc, "headers", None)
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    app_logger.exception("Unhandled server error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": request_id_var.get("-")},
    )

# Include routers
app.include_router(agent_router)
app.include_router(auth_router)

from routes.admin import router as admin_router
app.include_router(admin_router)

# Serve static files (frontend build) in production
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
    logger.info(f"Serving static files from {static_path}")
else:
    logger.info("No static directory found, running in API-only mode")


@app.get("/api")
async def api_root():
    """API root endpoint."""
    return {
        "name": "HF Agent API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    port = settings.PORT
    uvicorn.run(app, host="0.0.0.0", port=port)
