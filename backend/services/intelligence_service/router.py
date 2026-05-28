"""Intelligence service router."""

from fastapi import APIRouter

from app.api.enrichment import router as enrichment_router
from app.api.research import router as research_router

router = APIRouter(prefix="/api/v1")
router.include_router(enrichment_router)
router.include_router(research_router)

