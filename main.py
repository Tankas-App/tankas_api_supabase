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


# ---------------------------------------------------------------------------
# Lifespan — runs init_db() on startup, close_db() on shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Tankas API",
    description="Environmental cleanup coordination platform",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to production domain in Phase 3
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


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Custom OpenAPI schema — adds Bearer token Authorize button to Swagger UI
# ---------------------------------------------------------------------------


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title="Tankas API",
        version="0.2.0",
        description="Environmental cleanup coordination platform",
        routes=app.routes,
    )

    # Add the Bearer token security scheme
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your JWT token here. Get it from /api/auth/login or /api/auth/signup",
        }
    }

    # Apply it globally to all endpoints
    for path in schema["paths"].values():
        for method in path.values():
            method.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "Tankas API is running", "status": "ok", "version": "0.2.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
