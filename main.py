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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
