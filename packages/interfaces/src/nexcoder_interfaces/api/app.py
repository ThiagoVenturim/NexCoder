from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from faccoder_interfaces.api.routes import router
from faccoder_interfaces.registry import is_module_installed

logger = logging.getLogger(__name__)


def create_app(
    api_key: str | None = None,
    enforce_auth: bool | None = None,
    api_key_service: Any = None,
    auth_provider: Any = None,
    approval_token_manager: Any = None,
    insecure_local: bool = False,
    host: str = "127.0.0.1",
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the faccoder FastAPI application."""
    app = FastAPI(
        title="faccoder-interfaces",
        description="REST API and MCP server for the faccoder platform.",
        version="0.1.0",
    )

    # 1. CORS Configuration: No CORS by default; explicit origins only, never '*' with credentials
    if cors_origins is None:
        env_cors = os.environ.get("FACCODER_CORS_ORIGINS")
        if env_cors:
            cors_origins = [o.strip() for o in env_cors.split(",") if o.strip()]

    if cors_origins:
        has_wildcard = "*" in cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=not has_wildcard,  # Never allow credentials with wildcard origin
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 2. Insecure-local check & Auth determination
    if insecure_local or enforce_auth is False:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("--insecure-local mode is only permitted on 127.0.0.1 / localhost")
        logger.warning("INSECURE MODE: Running without authentication on %s", host)
        require_auth = False
    else:
        # HTTP servers must ALWAYS require authentication
        require_auth = True

    # 3. Control Plane Integration Setup
    has_control = is_module_installed("faccoder_control")

    if has_control:
        if api_key_service is None:
            try:
                from faccoder_control.keys import APIKeyService

                api_key_service = APIKeyService()
            except Exception as e:
                logger.debug("Could not initialize default APIKeyService: %s", e)

        if auth_provider is None:
            try:
                from faccoder_control.auth import LocalAuthProvider

                auth_provider = LocalAuthProvider()
            except Exception as e:
                logger.debug("Could not initialize default LocalAuthProvider: %s", e)

        if approval_token_manager is None:
            try:
                from faccoder_control.approval import ApprovalTokenManager

                approval_token_manager = ApprovalTokenManager()
            except Exception as e:
                logger.debug("Could not initialize default ApprovalTokenManager: %s", e)

    app.state.api_key_service = api_key_service
    app.state.auth_provider = auth_provider
    app.state.approval_token_manager = approval_token_manager

    # 4. Authentication Middleware
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        # Exclude public health checks and docs
        if not require_auth or path in ("/health", "/v1/health", "/docs", "/openapi.json"):
            request.state.is_human = True
            request.state.principal_name = "anonymous"
            return await call_next(request)

        provided_key: str | None = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization", "")
        bearer_token: str | None = None
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header[7:].strip()
            if not provided_key:
                provided_key = bearer_token

        if not provided_key and not bearer_token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Missing authentication credentials."},
            )

        authenticated = False
        principal_name = "unknown"
        is_human = False

        # Constant-time comparison for static API key if configured
        static_key = api_key or os.environ.get("FACCODER_API_KEY")
        if static_key and provided_key:
            if hmac.compare_digest(provided_key, static_key):
                authenticated = True
                principal_name = "static_key_user"
                is_human = False  # Static API key is machine/agent credential

        # Bearer token validation with control plane auth provider
        current_auth_provider = getattr(request.app.state, "auth_provider", None)
        if not authenticated and bearer_token and current_auth_provider is not None:
            try:
                principal = current_auth_provider.authenticate_bearer_token(bearer_token)
                authenticated = True
                principal_name = getattr(principal, "name", "bearer_user")
                is_human = getattr(principal, "is_human", True)
                request.state.principal = principal
            except Exception as exc:
                exc_type_name = type(exc).__name__
                if "AuthenticationError" in exc_type_name or "InvalidTokenError" in exc_type_name:
                    logger.debug("Bearer token verification failed: %s", exc)
                else:
                    logger.error("Bearer token verification error: %s", exc)
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "Service unavailable: Authentication verification error."},
                    )

        # API key verification with control plane APIKeyService
        current_key_service = getattr(request.app.state, "api_key_service", None)
        if not authenticated and provided_key and current_key_service is not None:
            try:
                record = current_key_service.verify_key(provided_key)
                authenticated = True
                principal_name = record.owner
                is_human = False  # API keys are machine/agent credentials
                request.state.api_key_record = record
            except Exception as exc:
                exc_type_name = type(exc).__name__
                if "AuthenticationError" in exc_type_name:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": f"Unauthorized: {exc}"},
                    )
                elif "ForbiddenError" in exc_type_name or "CapExceededError" in exc_type_name:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Forbidden: {exc}"},
                    )
                elif "RateLimitExceededError" in exc_type_name:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": f"Rate limit exceeded: {exc}"},
                    )
                else:
                    logger.error("APIKeyService verification error: %s", exc)
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "Service unavailable: Authentication system error."},
                    )

        if not authenticated:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or unverified API key or token."},
            )

        request.state.authenticated = True
        request.state.principal_name = principal_name
        request.state.is_human = is_human

        return await call_next(request)

    app.include_router(router)
    return app


app = create_app()
