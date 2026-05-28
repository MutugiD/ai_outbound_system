"""Identity service FastAPI app."""

from services.identity_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="identity-service",
    description="Tenant identity, authentication, and admin service.",
    router=router,
)

