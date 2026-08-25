import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.database import init_db, close_db
from app.routes import (
    auth,
    issues,
    test,
    volunteers,
    completion,
    collection,
    leaderboards,
)
from app.routes import payments, admin, pledges
from app.routes import comments, rewards, profile, public


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Tankas API",
    description="Environmental cleanup coordination platform",
    version="0.3.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
#
# `allow_origins=["*"]` together with `allow_credentials=True` is invalid per
# the CORS spec, and Starlette handles the pair inconsistently: preflight
# responses echo the caller's Origin, but actual responses still go out as
# `Access-Control-Allow-Origin: *`. A browser rejects that on any credentialed
# request, which surfaces as an opaque CORS failure in the console.
#
# List the allowed origins explicitly so both the preflight and the real
# response carry the same concrete origin. Override in deployment with
# CORS_ALLOW_ORIGINS as a comma-separated list.
# ---------------------------------------------------------------------------
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://tankas-web-production.up.railway.app",
]

_configured = os.getenv("CORS_ALLOW_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _configured.split(",") if o.strip()] or (
    DEFAULT_ALLOWED_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # Preview/branch deploys get generated subdomains, so match them by pattern
    # rather than pinning every one.
    allow_origin_regex=r"https://[a-z0-9-]+\.(up\.railway\.app|vercel\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(issues.router, prefix="/api")
app.include_router(test.router, prefix="/api")
app.include_router(volunteers.router, prefix="/api")
app.include_router(completion.router, prefix="/api")
app.include_router(collection.router, prefix="/api")
app.include_router(leaderboards.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(pledges.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(rewards.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(public.router, prefix="/api")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title="Tankas API",
        version="0.3.0",
        description="Environmental cleanup coordination platform",
        routes=app.routes,
    )

    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your JWT token here. Get it from /api/auth/login or /api/auth/signup",
        }
    }

    for path in schema["paths"].values():
        for method in path.values():
            method.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
async def root():
    return {"message": "Tankas API is running", "status": "ok", "version": "0.3.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
