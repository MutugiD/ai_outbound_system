"""Main API router aggregating all sub-routers under /api/v1."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.leads import router as leads_router
from app.api.companies import router as companies_router
from app.api.enrichment import router as enrichment_router
from app.api.research import router as research_router
from app.api.campaigns import router as campaigns_router
from app.api.outreach import router as outreach_router
from app.api.analytics import router as analytics_router
from app.api.admin import router as admin_router
from app.api.notifications import router as notifications_router
from app.api.export import router as export_router
from app.api.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(leads_router)
api_router.include_router(companies_router)
api_router.include_router(enrichment_router)
api_router.include_router(research_router)
api_router.include_router(campaigns_router)
api_router.include_router(outreach_router)
api_router.include_router(analytics_router)
api_router.include_router(admin_router)
api_router.include_router(notifications_router)
api_router.include_router(export_router)
api_router.include_router(tasks_router)
