from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from src.common.db import init_db
from src.dashboard_html import get_dashboard_html
from src.part1_auth.router import router as auth_router
from src.part2_catalog.router import router as catalog_router
from src.part3_subscriptions.router import router as subscriptions_router
from src.part4_billing.router import router as billing_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables and high-performance indexes are created
    init_db()
    yield

app = FastAPI(
    title="Brightloop Software - Subscription Management System",
    description="Unified recurring billing and subscription management platform built for Brightloop Software.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Visual Executive & Operations Web Dashboard
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def get_web_dashboard():
    return HTMLResponse(content=get_dashboard_html(), status_code=200)

# Health check endpoint
@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Brightloop Subscription Management System",
        "version": "1.0.0",
    }

# Mount all 4 decoupled domain modules under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
