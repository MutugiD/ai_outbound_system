"""Analytics service router."""

from fastapi import APIRouter

from app.api.analytics import router as analytics_router

router = APIRouter(prefix="/api/v1")
router.include_router(analytics_router)

