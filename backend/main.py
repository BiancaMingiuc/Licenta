"""Entry point of the Edge AI surveillance backend."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.database import initialize_database
from app.config.security import validate_security_configuration
from app.routers import (
    access_router,
    auth_router,
    camera_router,
    log_router,
    simulation_router,
    user_router,
)

CORS_ORIGINS_ENV = "ACCESS_CONTROL_CORS_ORIGINS"

# The default origins cover local development: Expo Web (8081), the older
# Expo port (19006) and a plain development server (3000).
# `allow_origins=["*"]` was replaced deliberately: on an API that holds
# biometric data and an intruder journal, an arbitrary web page open in the
# browser must not be able to send requests to the backend.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:19006",
    "http://127.0.0.1:19006",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def get_cors_origins() -> list[str]:
    """Allowed origins, configurable without code changes.

    On the Raspberry Pi, set ``ACCESS_CONTROL_CORS_ORIGINS`` to a
    comma-separated list (for example the hub address inside the VPN). The
    value ``*`` is only honoured when explicitly requested, so that a
    permissive setup is a conscious decision rather than a default.
    """
    configured = os.getenv(CORS_ORIGINS_ENV)
    if not configured:
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Apply any missing migrations before the first request is served.
    initialize_database()
    # Refuse to start when the signing secret is misconfigured, instead of
    # failing only at the first login attempt.
    validate_security_configuration()
    yield


app = FastAPI(
    title="Edge AI Surveillance API",
    version="0.5.0",
    description=(
        "Backend for a facial-recognition surveillance and intruder-alerting "
        "system. JWT authentication, three-tier RBAC "
        "(ADMIN / APP_USER / MONITORED), multi-tenant isolation through "
        "hub_id, and fail-loud detection with per-camera zone checks. "
        "The system observes and alerts; it does not grant physical access."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    # The token travels in the Authorization header rather than in cookies, so
    # the browser does not need permission to send credentials.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(camera_router.router)
app.include_router(log_router.router)
app.include_router(access_router.router)
app.include_router(simulation_router.router)


@app.get("/", tags=["Status"])
def root():
    """Quick availability check. Exposes no data and requires no token."""
    return {"message": "Edge AI Surveillance API is running successfully!"}
