"""AI Outbound Operating System - monolith compatibility FastAPI app."""

from app.api.router import api_router
from app.config import settings
from shared.app_factory import create_service_app

app = create_service_app(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI Outbound Operating System API",
    router=api_router,
)
