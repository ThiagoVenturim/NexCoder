from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from faccoder_interfaces.api.routes import router
from faccoder_interfaces.registry import is_module_installed

logger = logging.getLogger(__name__)


def create_app(
    api_key: str | None = None,
    enforce_auth: bool | None = None,
) -> FastAPI:
    """Create and configure the faccoder FastAPI application."""
    app = FastAPI(
        title="faccoder-interfaces",
        description="REST API and MCP server for the faccoder platform.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Determine whether authentication is enforced
    has_control = is_module_installed("faccoder_control")
    env_key = os.environ.get("FACCODER_API_KEY")
    expected_key = api_key or env_key

    # Enforce auth if control plane is installed, FACCODER_API_KEY is defined, or enforce_auth is True
    require_auth = enforce_auth if enforce_auth is not None else (has_control or bool(env_key))

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Exclude public health checks and MCP SSE root
        path = request.url.path
        if not require_auth or path in ("/health", "/v1/health", "/docs", "/openapi.json"):
            return await call_next(request)

        provided_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization", "")
        if not provided_key and auth_header.startswith("Bearer "):
            provided_key = auth_header[7:].strip()

        # If control plane installed and has an authenticator, delegate to it
        if has_control:
            try:
                from faccoder_control.auth import verify_api_key  # type: ignore

                if not verify_api_key(provided_key):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Unauthorized: API key verification failed."},
                    )
            except Exception as exc:
                # If control auth verification import fails, fall back to expected_key check
                logger.debug("Control plane auth check bypassed: %s", exc)

        if expected_key and provided_key != expected_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing API key."},
            )

        return await call_next(request)

    app.include_router(router)
    return app


app = create_app()
