from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, issues, test

# Create the FastAPI application
app = FastAPI(
    title="Tankas API",
    description="Environmental cleanup coordination platform",
    version="0.1.0"
)

# Configure CORS (Cross-Origin Resource Sharing)
# This allows your frontend to communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers from different modules
app.include_router(auth.router, prefix="/api")
app.include_router(issues.router, prefix="/api")
app.include_router(test.router, prefix="/api")

# Health check endpoint
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Tankas API is running",
        "status": "ok",
        "version": "0.1.0"
    }

@app.get("/health")
async def health():
    """Health check endpoint for monitoring"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # Run the server with: python main.py
    uvicorn.run(app, host="0.0.0.0", port=8000)