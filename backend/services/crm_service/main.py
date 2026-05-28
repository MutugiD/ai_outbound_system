"""CRM service FastAPI app."""

from services.crm_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="crm-service",
    description="Companies, contacts, leads, notes, and pipeline service.",
    router=router,
)

