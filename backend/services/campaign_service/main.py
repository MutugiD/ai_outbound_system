"""Campaign service FastAPI app."""

from services.campaign_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="campaign-service",
    description="Campaign, enrollment, follow-up, and queue orchestration service.",
    router=router,
)

