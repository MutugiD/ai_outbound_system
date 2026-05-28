"""CRM service router."""

from fastapi import APIRouter

from app.api.companies import router as companies_router
from app.api.contacts import router as contacts_router
from app.api.leads import router as leads_router
from app.api.notes import router as notes_router

router = APIRouter(prefix="/api/v1")
router.include_router(leads_router)
router.include_router(companies_router)
router.include_router(contacts_router)
router.include_router(notes_router)

