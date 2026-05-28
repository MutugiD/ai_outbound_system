"""Intelligence service FastAPI app."""

from services.intelligence_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="intelligence-service",
    description="AI enrichment, research, scoring, and reply intelligence service.",
    router=router,
)

