"""Factory for creating per-domain FastAPI applications."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply a shared security header policy to every backend service."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        return response


def create_service_app(
    *,
    title: str,
    description: str,
    version: Optional[str] = None,
    router: Optional[APIRouter] = None,
) -> FastAPI:
    """Create a FastAPI app with shared middleware and health/version endpoints."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        yield

    app = FastAPI(
        title=title,
        version=version or settings.VERSION,
        description=description,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if router is not None:
        app.include_router(router)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "service": title}

    @app.get("/version", tags=["health"])
    async def version_check():
        return {
            "version": settings.VERSION,
            "app_version": settings.APP_VERSION or settings.VERSION,
            "git_sha": settings.GIT_SHA,
            "service": title,
        }

    return app

