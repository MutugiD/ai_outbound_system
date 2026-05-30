"""WhatsApp session management and messaging API endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.whatsapp_session import WhatsAppSession
from app.models.lead import Lead
from app.models.message import OutreachMessage
from app.services.whatsapp.evolution_client import EvolutionClient
from pydantic import BaseModel

router = APIRouter(prefix="/channel/whatsapp", tags=["whatsapp"])


# ── Schemas ─────────────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    instance_name: str


class SessionResponse(BaseModel):
    id: str
    instance_name: str
    phone_number: Optional[str] = None
    status: str
    qr_code: Optional[str] = None
    paired_at: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class SendTextRequest(BaseModel):
    lead_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    phone: str  # e.g. "254712345678"
    text: str


class SendTextResponse(BaseModel):
    status: str
    evolution_key: Optional[dict] = None
    message_id: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────────


def _session_response(session: WhatsAppSession) -> dict:
    return {
        "id": str(session.id),
        "instance_name": session.instance_name,
        "phone_number": session.phone_number,
        "status": session.status,
        "qr_code": session.qr_code,
        "paired_at": session.paired_at.isoformat() if session.paired_at else None,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


async def _get_connected_session(
    team_id: uuid.UUID,
    db: AsyncSession,
) -> WhatsAppSession:
    """Find the first connected WhatsApp session for a team."""
    result = await db.execute(
        select(WhatsAppSession).where(
            WhatsAppSession.team_id == team_id,
            WhatsAppSession.status == "connected",
        )
    )
    return result.scalar_one_or_none()


# ── Session Endpoints ───────────────────────────────────────────────────────


@router.get("/health")
async def whatsapp_health():
    """Check Evolution API connectivity."""
    client = EvolutionClient()
    result = await client.healthcheck()
    await client.close()
    return result


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: Request,
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new WhatsApp session (Evolution API instance)."""
    # Check if instance_name already exists for this team
    existing = await db.execute(
        select(WhatsAppSession).where(
            WhatsAppSession.instance_name == body.instance_name,
            WhatsAppSession.team_id == current_user.team_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Instance name already exists for this team")

    client = EvolutionClient()
    try:
        # Create instance in Evolution API (requires WHATSAPP-BAILEYS integration)
        await client.create_instance(body.instance_name)

        # Register per-instance webhook so QR/connection/message events reach our backend
        webhook_url = str(request.base_url).rstrip("/") + "/api/v1/webhooks/whatsapp"
        try:
            await client.configure_webhook(body.instance_name, webhook_url)
        except Exception:
            pass  # Webhook may already exist; non-fatal

        # Connect to trigger QR code generation
        try:
            await client.connect_instance(body.instance_name)
        except Exception:
            pass  # Connection may fail initially; QR arrives via webhook

        # Try to get QR code immediately (may not be ready yet)
        qr_code = None
        try:
            qr_result = await client.get_qr_code(body.instance_name)
            qr_code = qr_result.get("qrcode", qr_result.get("base64", ""))
        except Exception:
            # QR code will arrive via webhook and be stored in DB
            pass

        # Persist session in our DB
        session = WhatsAppSession(
            team_id=current_user.team_id,
            instance_name=body.instance_name,
            status="connecting",
            qr_code=qr_code,
            created_by=current_user.id,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return _session_response(session)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Evolution API error: {e}")
    finally:
        await client.close()


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all WhatsApp sessions for the current team."""
    result = await db.execute(
        select(WhatsAppSession)
        .where(WhatsAppSession.team_id == current_user.team_id)
        .order_by(WhatsAppSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return {"items": [_session_response(s) for s in sessions], "total": len(sessions)}


@router.get("/sessions/{session_id}/qr")
async def get_session_qr(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get QR code for a WhatsApp session."""
    session = await db.get(WhatsAppSession, session_id)
    if not session or session.team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="Session not found")

    client = EvolutionClient()
    try:
        # Refresh QR code from Evolution API
        qr_result = await client.get_qr_code(session.instance_name)
        qr_code = qr_result.get("qrcode", qr_result.get("base64", ""))

        session.qr_code = qr_code
        session.updated_at = datetime.utcnow()
        db.add(session)
        await db.flush()

        return {"qr_code": qr_code, "status": session.status}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Evolution API error: {e}")
    finally:
        await client.close()


@router.get("/sessions/{session_id}/status")
async def get_session_status(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check live connection status from Evolution API."""
    session = await db.get(WhatsAppSession, session_id)
    if not session or session.team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="Session not found")

    client = EvolutionClient()
    try:
        status_result = await client.instance_status(session.instance_name)
        state = status_result.get("instance", {}).get("state", "unknown")

        # Map Evolution API states to our statuses
        state_map = {
            "open": "connected",
            "connecting": "connecting",
            "close": "disconnected",
            "disconnected": "disconnected",
            "logged-out": "disconnected",
        }
        session.status = state_map.get(state, state)
        session.last_ping = datetime.utcnow()
        session.updated_at = datetime.utcnow()

        # If connected and we don't have phone number, try to fetch it
        if session.status == "connected" and not session.phone_number:
            instances = await client.fetch_instances()
            for inst in instances:
                if inst.get("instance", {}).get("name") == session.instance_name:
                    phone = inst.get("instance", {}).get("phone") or inst.get("instance", {}).get("number", "")
                    if phone:
                        session.phone_number = phone
                    break

        db.add(session)
        await db.flush()
        return _session_response(session)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Evolution API error: {e}")
    finally:
        await client.close()


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnect and delete a WhatsApp session."""
    session = await db.get(WhatsAppSession, session_id)
    if not session or session.team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="Session not found")

    client = EvolutionClient()
    try:
        await client.disconnect_instance(session.instance_name)
        await client.delete_instance(session.instance_name)
    except Exception:
        # Best effort -- instance may already be gone
        pass
    finally:
        await client.close()

    await db.delete(session)
    return {"status": "deleted", "instance_name": session.instance_name}


# ── Messaging Endpoints ──────────────────────────────────────────────────────


@router.post("/send", response_model=SendTextResponse)
async def send_whatsapp_message(
    body: SendTextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a WhatsApp message via Evolution API."""
    # Get a connected session
    session = await _get_connected_session(current_user.team_id, db)
    if not session:
        raise HTTPException(status_code=400, detail="No connected WhatsApp session. Create and scan QR first.")

    # Verify lead belongs to this team
    lead = await db.get(Lead, body.lead_id)
    if not lead or lead.team_id != current_user.team_id:
        raise HTTPException(status_code=404, detail="Lead not found")

    client = EvolutionClient()
    try:
        result = await client.send_text(session.instance_name, body.phone, body.text)

        # Update OutreachMessage if one was provided
        if body.message_id:
            message = await db.get(OutreachMessage, body.message_id)
            if message:
                message.status = "sent"
                message.channel = "whatsapp"
                message.provider = "evolution-api"
                message.provider_message_id = result.get("key", {}).get("id")
                message.sent_at = datetime.utcnow()
                db.add(message)

        # Update session ping
        session.last_ping = datetime.utcnow()
        db.add(session)

        return SendTextResponse(
            status="sent",
            evolution_key=result.get("key"),
            message_id=result.get("key", {}).get("id"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Evolution API send error: {e}")
    finally:
        await client.close()
