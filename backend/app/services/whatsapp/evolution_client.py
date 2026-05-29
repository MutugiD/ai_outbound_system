"""HTTP client wrapping Evolution API for WhatsApp messaging."""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EvolutionClient:
    """Low-level HTTP client for Evolution API."""

    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL.rstrip("/")
        self.api_key = settings.EVOLUTION_API_KEY
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "apikey": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Instance / Session ─────────────────────────────────────────────

    async def create_instance(self, instance_name: str) -> dict:
        """Create a new WhatsApp instance (WHATSAPP-BAILEYS integration)."""
        client = await self._get_client()
        resp = await client.post(
            "/instance/create",
            json={"instanceName": instance_name, "integration": "WHATSAPP-BAILEYS"},
        )
        resp.raise_for_status()
        return resp.json()

    async def configure_webhook(self, instance_name: str, webhook_url: str) -> dict:
        """Register a per-instance webhook so Evolution API sends events to our backend.

        Without this, the global webhook may not fire QRCODE_UPDATED and other
        events for this specific instance.
        """
        client = await self._get_client()
        resp = await client.post(
            f"/webhook/set/{instance_name}",
            json={
                "webhook": {
                    "url": webhook_url,
                    "enabled": True,
                    "webhookByEvents": True,
                    "events": [
                        "APPLICATION_STARTUP",
                        "QRCODE_UPDATED",
                        "CONNECTION_UPDATE",
                        "MESSAGES_UPSERT",
                        "SEND_MESSAGE",
                    ],
                }
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def connect_instance(self, instance_name: str) -> dict:
        """Connect instance to trigger QR code generation (GET in v2.2.3)."""
        client = await self._get_client()
        resp = await client.get(f"/instance/connect/{instance_name}")
        resp.raise_for_status()
        return resp.json()

    async def disconnect_instance(self, instance_name: str) -> dict:
        """Disconnect and logout the instance (DELETE in v2.2.3)."""
        client = await self._get_client()
        resp = await client.delete(f"/instance/logout/{instance_name}")
        resp.raise_for_status()
        return resp.json()

    async def delete_instance(self, instance_name: str) -> dict:
        """Delete an instance entirely."""
        client = await self._get_client()
        resp = await client.delete(f"/instance/delete/{instance_name}")
        resp.raise_for_status()
        return resp.json()

    async def get_qr_code(self, instance_name: str) -> dict:
        """Get QR code for instance pairing."""
        client = await self._get_client()
        resp = await client.get(f"/instance/qrcode/{instance_name}")
        resp.raise_for_status()
        return resp.json()

    async def fetch_instances(self) -> list:
        """List all instances and their connection status."""
        client = await self._get_client()
        resp = await client.get("/instance/fetchInstances")
        resp.raise_for_status()
        return resp.json()

    async def instance_status(self, instance_name: str) -> dict:
        """Get connection status of a specific instance."""
        client = await self._get_client()
        resp = await client.get(f"/instance/connectionState/{instance_name}")
        resp.raise_for_status()
        return resp.json()

    # ── Messaging ─────────────────────────────────────────────────────

    async def send_text(self, instance_name: str, number: str, text: str) -> dict:
        """Send a text message.

        Args:
            instance_name: Evolution API instance name.
            number: Phone number in format country_code+number, e.g. "254712345678".
            text: Message body.
        """
        client = await self._get_client()
        resp = await client.post(
            f"/message/sendText/{instance_name}",
            json={"number": number, "text": text},
        )
        resp.raise_for_status()
        return resp.json()

    async def send_media(
        self, instance_name: str, number: str, media_type: str, media_url: str, caption: str = ""
    ) -> dict:
        """Send a media message (image, document, audio, video)."""
        client = await self._get_client()
        endpoint_map = {
            "image": "/message/sendMedia/{instance}",
            "document": "/message/sendMedia/{instance}",
            "audio": "/message/sendWhatsAppAudio/{instance}",
            "video": "/message/sendMedia/{instance}",
        }
        endpoint = endpoint_map.get(media_type, "/message/sendMedia/{instance}").replace("{instance}", instance_name)
        payload = {
            "number": number,
            "mediatype": media_type,
            "media": media_url,
            "caption": caption,
        }
        resp = await client.post(endpoint, json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Contact / Phone ───────────────────────────────────────────────

    async def check_number_exists(self, instance_name: str, number: str) -> dict:
        """Check if a phone number is registered on WhatsApp."""
        client = await self._get_client()
        resp = await client.post(
            f"/chat/whatsappNumbers/{instance_name}",
            json={"numbers": [number]},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_profile_picture(self, instance_name: str, number: str) -> dict:
        """Get profile picture URL for a number."""
        client = await self._get_client()
        resp = await client.get(f"/chat/fetchProfilePictureUrl/{instance_name}?number={number}")
        resp.raise_for_status()
        return resp.json()

    # ── Healthcheck ───────────────────────────────────────────────────

    async def healthcheck(self) -> dict:
        """Check if Evolution API is running."""
        client = await self._get_client()
        try:
            resp = await client.get("/", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            return {"status": "ok", "version": data.get("version", "unknown")}
        except Exception as e:
            logger.warning("Evolution API healthcheck failed: %s", e)
            return {"status": "error", "message": str(e)}
