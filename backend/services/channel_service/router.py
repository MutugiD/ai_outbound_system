"""Channel service router."""

from fastapi import APIRouter

from app.api.inbox import router as inbox_router
from app.api.webhooks import router as webhooks_router

router = APIRouter(prefix="/api/v1")
router.include_router(inbox_router)
router.include_router(webhooks_router)

