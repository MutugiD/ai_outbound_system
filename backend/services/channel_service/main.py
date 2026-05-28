"""Channel service FastAPI app."""

from services.channel_service.router import router
from shared.app_factory import create_service_app

app = create_service_app(
    title="channel-service",
    description="Message delivery, inbound webhooks, and channel state service.",
    router=router,
)

