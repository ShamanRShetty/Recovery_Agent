"""
FastAPI Backend Entrypoint (Phase 6)
=====================================

Application entrypoint exposing the Subscription Recovery Agent API surface,
including general endpoints and signature-verified Razorpay webhook routes.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import router as api_router
from api.webhooks import router as webhook_router

app = FastAPI(
    title="Recoup — Razorpay Failed Subscription Recovery Agent API",
    description="AI-assisted backend for failed subscription classification, policy decisions, action execution, and audit logging.",
    version="1.0.0"
)

# Enable CORS for local development (frontend support)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# Wire up routers
app.include_router(api_router)
app.include_router(webhook_router)

@app.get("/")
def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
