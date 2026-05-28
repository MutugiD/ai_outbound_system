"""Acquisition service FastAPI app."""

from services.acquisition_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="acquisition-service",
    description="Source management, scrape jobs, and raw acquisition data service.",
    router=router,
)
