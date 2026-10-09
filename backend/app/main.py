"""FastAPI app entrypoint — THE MAIN OCR backend."""

import os

# Must run before paddle/numpy import anywhere in the process.
os.environ.setdefault("OMP_NUM_THREADS", "6")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "6")
os.environ.setdefault("MKL_NUM_THREADS", "6")
os.environ.setdefault("PADDLE_PDX_CPU_NUM_THREADS", "6")

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.logging_config import configure_logging
from app.core.rate_limit import limiter
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.upload_limit import BODY_TOO_BIG_DETAIL, UploadSizeLimitMiddleware
from app.features.admin.router import router as admin_router
from app.features.auth.router import router as auth_router
from app.features.documents.recovery import recover_interrupted_documents
from app.features.documents.router import MAX_FILE_SIZE
from app.features.documents.router import router as documents_router

configure_logging()


async def _recover_in_background() -> None:
    """Never lets a recovery problem touch startup or request handling - log and move on."""
    try:
        await recover_interrupted_documents()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Restart recovery failed - interrupted documents were left as they were")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    await connect_to_mongo()
    recovery_task: asyncio.Task[None] | None = None
    if settings.recover_interrupted_uploads:
        # A background task, NOT awaited: startup completes and /health answers immediately
        # while any interrupted documents are re-queued one by one behind the scenes.
        recovery_task = asyncio.create_task(_recover_in_background())
    app.state.recovery_task = recovery_task
    logger.info("Application startup complete (env={})", settings.environment)
    yield
    logger.info("Application shutdown")
    if recovery_task is not None and not recovery_task.done():
        recovery_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recovery_task
    await close_mongo_connection()


app = FastAPI(
    title="THE MAIN OCR",
    version="0.1.0",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Whole-request ceiling for the upload route (two files + multipart framing). Runs before the
# body is parsed, so an oversized request is refused with 413 instead of being buffered first;
# the per-file 5 MB rule and type checks still live in the route itself.
_MULTIPART_OVERHEAD = 1024 * 1024
app.add_middleware(
    UploadSizeLimitMiddleware,
    limits={"/api/documents/upload": 2 * MAX_FILE_SIZE + _MULTIPART_OVERHEAD},
)
# Every auth request is a few short strings; cap the whole body so nobody can make the server
# buffer megabytes of JSON on /login or /signup before validation even starts.
_AUTH_BODY_LIMIT = 16 * 1024
app.add_middleware(
    UploadSizeLimitMiddleware,
    limits={
        f"/api/auth/{route}": _AUTH_BODY_LIMIT
        for route in (
            "signup",
            "login",
            "change-password",
            "forgot-password/verify",
            "forgot-password/reset",
            "me",
        )
    },
    detail=BODY_TOO_BIG_DETAIL,
)
app.add_middleware(SecurityHeadersMiddleware, is_production=settings.is_production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Included-Count", "X-Skipped-Count"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Only where / what / which rule - never pydantic's `input` (the rejected value). Echoing it
    # would send a mistyped password straight back in the response body, and a value that can't
    # be encoded as UTF-8 (a lone surrogate) used to turn this very handler into a 500.
    errors = [
        {
            "loc": list(e.get("loc", ())),
            "msg": e.get("msg", "Invalid value."),
            "type": e.get("type"),
        }
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "modelType": settings.model_type}


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(documents_router, prefix="/api/documents", tags=["documents"])
