"""Analytics service FastAPI app."""

from services.analytics_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="analytics-service",
    description="Reporting and service health analytics.",
    router=router,
)
