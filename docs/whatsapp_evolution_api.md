# WhatsApp Integration via Evolution API

## Why Unofficial

The official WhatsApp Business API requires:
- Facebook Business Manager verification
- App review process (weeks to months)
- Per-message pricing
- Template pre-approval for outbound messages

For our use case (AI outbound sales platform targeting Kenyan SMBs), the approval timeline and template restrictions make the official API impractical for MVP. The workaround uses the same WebSocket protocol that WhatsApp Web uses, paired with a real phone number.

> **Warning**: This approach is technically against WhatsApp Terms of Service. WhatsApp can ban accounts that send high volumes to unsaved contacts. Start with low volume and warm up gradually.

---

## Research Summary: Unofficial WhatsApp Libraries

### Tier 1: WebSocket Protocol Libraries (no browser needed)

| Library | Stars | Language | Approach | Status |
|---------|-------|----------|----------|--------|
| **Baileys** (WhiskeySockets/Baileys) | 9,577 | JS/TS | Direct WebSocket protocol for WhatsApp Web | Active (updated May 2026) |
| **neonize** (krypton-byte/neonize) | 398 | Python | Python wrapper around Baileys via Go bridge | Active (updated May 2026) |

Baileys reverse-engineers the WhatsApp Web binary protocol. It connects using the same WebSocket that the WhatsApp web client uses. No Puppeteer, no browser -- lightweight and fast. Supports text, media, documents, locations, contacts, reactions, polls, presence, and group management. Multi-device support. Auth state persisted to file (sessions survive restarts). Pairing via QR code scan or phone number + pairing code.

### Tier 2: HTTP API Servers (best for FastAPI backend integration)

| Library | Stars | Language | Engine | Status |
|---------|-------|----------|--------|--------|
| **Evolution API** (evolution-foundation/evolution-api) | 8,470 | TypeScript | Baileys | Active (updated May 2026) |
| **WAHA** (devlikeapro/waha) | 6,642 | TypeScript | Baileys + Puppeteer + Go | Active |
| **WppConnect Server** (wppconnect-team/wppconnect-server) | 1,036 | TypeScript | Puppeteer | Active |

Evolution API and WAHA both wrap Baileys with a REST API server. Your backend makes HTTP calls. Webhook support for inbound messages. Docker-ready. Multi-session (one per phone number). Management dashboards.

### Tier 3: Browser Automation (heaviest, most fragile)

| Library | Stars | Language | Approach | Status |
|---------|-------|----------|----------|--------|
| **whatsapp-web.js** (wwebjs/whatsapp-web.js) | 21,917 | JS | Puppeteer-controls Chrome loading web.whatsapp.com | Active |
| **PyWhatsapp** (shauryauppal/PyWhatsapp) | 494 | Python | Selenium automation of WhatsApp Web UI | Semi-active |

Browser automation works but is heavy (needs Chromium), slow to start, and fragile to WhatsApp UI changes. Not recommended for production outbound.

---

## Chosen Solution: Evolution API

### Why Evolution API over alternatives

1. **Highest adoption** (8.5k stars, largest community)
2. **REST API** -- clean HTTP integration with our FastAPI backend, no Node.js interop needed
3. **Docker-ready** -- runs as a sidecar container alongside our existing PostgreSQL/Redis/MinIO
4. **Webhook support** -- posts inbound messages to our backend automatically
5. **Multi-session** -- support multiple phone numbers if needed
6. **Baileys-based** -- no browser needed, low resource usage
7. **Dashboard UI** -- for session management and QR scanning
8. **Active maintenance** -- commits within days, large issue tracker community

### Why NOT the other options

- **Baileys directly**: Requires Node.js runtime alongside our Python backend. Adds complexity. Evolution API wraps it cleanly.
- **WAHA**: Solid alternative, slightly fewer features, less community traction. Viable fallback.
- **neonize**: Python Baileys wrapper but lower adoption, less battle-tested for production outbound.
- **whatsapp-web.js / Puppeteer**: Too heavy, needs headless Chrome. Fragile to UI changes.
- **Selenium bots**: Toy projects, not production-ready.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  docker-compose.yml                                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  API Server   │  │  Evolution   │  │  Frontend    │              │
│  │  (FastAPI)    │  │  API         │  │  (React)     │              │
│  │  :8000        │  │  :8080       │  │  :5173       │              │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘              │
│         │                  │                                        │
│         │  HTTP POST       │  WebSocket                            │
│         │  (send message)  │  (to WhatsApp servers)                │
│         │                  │                                        │
│         │  POST webhook    │  QR code / pairing                    │
│         │  (inbound msg)   │  session auth                          │
│         │◄─────────────────│                                        │
│         │                  │                                        │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────────────┐              │
│  │  PostgreSQL  │  │  Redis       │  │  MinIO        │              │
│  │  :5432       │  │  :6379       │  │  :9000        │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow: Outbound

```
1. Campaign engine creates OutreachMessage (channel=whatsapp, status=approved)
2. Celery task picks up message from channel queue
3. Task calls Evolution API: POST /message/sendText/{instance}
   Body: { number: "254712345678", text: "Hello ..." }
4. Evolution API sends via WhatsApp Web protocol
5. Evolution API posts delivery webhook back to our /api/v1/webhooks/whatsapp
6. We update OutreachMessage status (sent -> delivered -> read)
```

### Data Flow: Inbound

```
1. Contact replies on WhatsApp
2. WhatsApp servers push to Evolution API WebSocket connection
3. Evolution API POSTs to our webhook: /api/v1/webhooks/whatsapp
   Body: { event: "messages.upsert", data: { key, message, pushName } }
4. Our webhook handler:
   a. Find Contact by whatsapp_phone (normalized)
   b. Find or create Reply record (channel=whatsapp)
   c. Enqueue classification Celery task
5. ReplyClassifier processes, creates ReplyClassification
6. FollowUpAutomation generates follow-up tasks
```

### Session Management

```
1. Admin creates session: POST /api/v1/channel/whatsapp/sessions
2. Backend calls Evolution API: POST /instance/create { instanceName }
3. Backend calls: POST /instance/connect/{instanceName}
4. Evolution API returns QR code
5. Admin scans QR with phone via Evolution API dashboard or our frontend
6. Session saved -- auth state persisted in Evolution API's storage
7. Backend tracks session status in our DB
```

---

## API Endpoints to Implement

### Backend (channel_service + webhooks)

```
# Session management
POST   /api/v1/channel/whatsapp/sessions              Create new WhatsApp session
GET    /api/v1/channel/whatsapp/sessions               List sessions + status
GET    /api/v1/channel/whatsapp/sessions/{id}/qr       Get QR code for scanning
DELETE /api/v1/channel/whatsapp/sessions/{id}           Disconnect + delete session

# Messaging
POST   /api/v1/channel/whatsapp/send                    Send WhatsApp message
  Body: { lead_id, message_id?, phone, text }

# Inbound webhook (called BY Evolution API, not JWT-protected)
POST   /api/v1/webhooks/whatsapp                        Receive inbound messages + delivery receipts

# Health
GET    /api/v1/channel/whatsapp/health                   Check Evolution API connectivity
```

---

## Docker Compose Addition

```yaml
  # ── Evolution API (WhatsApp) ────────────────────────────────────
  evolution-api:
    image: atendai/evolution-api:latest
    ports:
      - "8080:8080"
    environment:
      - SERVER_TYPE=http
      - SERVER_PORT=8080
      - DATABASE_ENABLED=true
      - DATABASE_PROVIDER=postgresql
      - DATABASE_CONNECTION_URI=postgresql://outbound:outbound@db:5432/evolution_api
      - DATABASE_PREFIX=evolution
      - WEBHOOK_GLOBAL_ENABLED=true
      - WEBHOOK_GLOBAL_URL=http://api-dev:8000/api/v1/webhooks/whatsapp
      - WEBHOOK_EVENTS_MESSAGE_UPSERT=true
      - WEBHOOK_EVENTS_MESSAGE_UPDATE=true
      - WEBHOOK_EVENTS_SEND_MESSAGE=true
      - WEBHOOK_EVENTS_CONNECTION_UPDATE=true
      - WEBHOOK_EVENTS_QR_CODE=true
      - AUTHENTICATION_TYPE=apikey
      - AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY:-outbound-os-evolution-key}
      - LANGUAGE=en
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - evolution_store:/evolution-store
```

---

## Database Changes

### New table: whatsapp_sessions

```sql
CREATE TABLE whatsapp_sessions (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id   UUID NOT NULL REFERENCES teams(id),
    instance_name VARCHAR(100) NOT NULL UNIQUE,
    phone_number VARCHAR(50),
    status    VARCHAR(20) DEFAULT 'disconnected',  -- disconnected, connecting, connected, banned
    qr_code   TEXT,
    paired_at TIMESTAMPTZ,
    last_ping TIMESTAMPTZ,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_whatsapp_sessions_team ON whatsapp_sessions(team_id);
CREATE INDEX idx_whatsapp_sessions_status ON whatsapp_sessions(status);
```

### Existing tables: no schema changes needed

- `contacts.whatsapp_phone` -- already exists
- `outreach_messages.channel` -- already supports 'whatsapp'
- `replies.channel` -- already supports 'whatsapp'
- `lead_source` -- provenance preserved on CRM promotion

---

## Environment Variables

Add to `backend/.env`:

```
# ── Evolution API (WhatsApp) ──
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=outbound-os-evolution-key
```

Add to `backend/.env.example`:

```
# ── Evolution API (WhatsApp) ──
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=your-evolution-api-key
```

---

## Implementation Plan

### Phase 1: Infrastructure + Session Management
1. Add Evolution API to docker-compose.yml
2. Create whatsapp_sessions Alembic migration
3. Create `backend/app/services/whatsapp/evolution_client.py` -- HTTP client wrapping Evolution API
4. Create `backend/app/api/whatsapp_sessions.py` -- session CRUD + QR code endpoints
5. Register routes in router.py
6. Test: create session, get QR, scan with phone, verify connected

### Phase 2: Outbound Messaging
1. Create `backend/app/services/whatsapp/whatsapp_sender.py` -- send message via Evolution API
2. Create Celery task in channel_service for WhatsApp sends
3. Wire into existing campaign engine -- when channel=whatsapp, route to WhatsApp sender
4. Update OutreachMessage with provider metadata (instance_name, provider_message_id)
5. Add WhatsApp webhook handler to webhooks.py for delivery receipts
6. Test: send a message to a known number, verify delivery

### Phase 3: Inbound Messaging
1. Create `POST /api/v1/webhooks/whatsapp` endpoint
2. Handle messages.upsert events -- find Contact by phone, create Reply
3. Enqueue ReplyClassifier task for inbound WhatsApp replies
4. Wire FollowUpAutomation for WhatsApp reply classification
5. Test: reply from phone, verify Reply record created and classified

### Phase 4: Frontend
1. Add WhatsApp session management to Settings page
2. Add WhatsApp channel option in campaign creation with phone preview
3. Add WhatsApp message column to inbox/replies view
4. Add WhatsApp delivery status indicators

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Account ban (spam detection) | High | Start at 10-20 msgs/day. Warm up over 2-4 weeks. Never send to people who haven't interacted. Randomize timing (30-120s between sends). |
| Session disconnection | Medium | Evolution API auto-reconnects. Add healthcheck endpoint. Celery task checks session status every 60s. Alert on disconnect. |
| WhatsApp protocol changes | Medium | Baileys/Evolution API community updates quickly (days). Pin Docker image tags. Test before upgrading. |
| Rate limiting by WhatsApp | High | Enforce per-session daily limits in our campaign engine. Queue sends with delays. Monitor for "slow down" signals. |
| Legal/ToS violation | Medium | Document internally. Don't advertise as "WhatsApp integration". Use for warm outreach only (contacts who opted in or have existing relationship). |
| Phone must stay connected | Low | Multi-device mode means phone only needs internet, doesn't need WhatsApp open. |

---

## Testing Guide

### Prerequisites
- A spare phone number with WhatsApp installed (NOT your primary number)
- Docker and docker-compose running
- Backend and infrastructure containers running

### Step 1: Start Evolution API

```bash
cd ai_outbound_system
docker compose up -d evolution-api
# Wait 10-15 seconds for startup
curl http://localhost:8080/healthcheck
# Should return: { "status": 200, "message": "Evolution API is running" }
```

### Step 2: Create a WhatsApp Session

```bash
# Create instance
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: outbound-os-evolution-key" \
  -H "Content-Type: application/json" \
  -d '{"instanceName": "outbound-os-1"}'

# Connect instance (get QR code)
curl -X POST http://localhost:8080/instance/connect/outbound-os-1 \
  -H "apikey: outbound-os-evolution-key"

# Get QR code as base64
curl -X GET http://localhost:8080/instance/qrcode/outbound-os-1 \
  -H "apikey: outbound-os-evolution-key"
```

### Step 3: Scan QR Code
- Open WhatsApp on your spare phone
- Go to Linked Devices > Link a Device
- Scan the QR code from Step 2 (display it in browser or decode the base64)
- Wait for "connected" status

### Step 4: Verify Connection

```bash
curl http://localhost:8080/instance/fetchInstances \
  -H "apikey: outbound-os-evolution-key"
# Should show your instance with connectionStatus: "open"
```

### Step 5: Send a Test Message

```bash
# Send text message (replace phone with your test target)
curl -X POST http://localhost:8080/message/sendText/outbound-os-1 \
  -H "apikey: outbound-os-evolution-key" \
  -H "Content-Type: application/json" \
  -d '{"number": "254712345678", "text": "Hello from AI Outbound OS test!"}'

# Phone number format: country code + number, no + or spaces
# Kenya = 254, so 254712345678
```

### Step 6: Test Inbound Webhook

```bash
# Start a simple webhook listener to see what Evolution API posts
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        print(json.dumps(json.loads(body), indent=2))
        self.send_response(200)
        self.end_headers()
HTTPServer(('0.0.0.0', 9999), Handler).serve_forever()
" &

# Now send a message TO the WhatsApp number linked in Step 3
# From another phone, send "Hi test" to your linked number
# You should see the webhook payload printed in the terminal
```

### Step 7: Test Via Our Backend API (after implementation)

```bash
# Create session via our API
curl -X POST http://localhost:8000/api/v1/channel/whatsapp/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance_name": "outbound-os-1"}'

# Get QR code
curl http://localhost:8000/api/v1/channel/whatsapp/sessions/{id}/qr \
  -H "Authorization: Bearer $TOKEN"

# Send message
curl -X POST http://localhost:8000/api/v1/channel/whatsapp/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"lead_id": "...", "phone": "254712345678", "text": "Test from outbound OS"}'
```

---

## Volume Ramp-Up Schedule

| Week | Daily Messages | Notes |
|------|---------------|-------|
| 1 | 10 | Only to saved contacts / warm leads |
| 2 | 20 | Mix of saved + 1-2 cold |
| 3 | 40 | Increase if no warnings |
| 4 | 60 | Add 30-120s random delay between sends |
| 5+ | 80-100 | Monitor for any rate-limit signals |

Never exceed 100 messages/day per session to minimize ban risk.

---

## Fallback: If Evolution API Goes Down

If Evolution API stops being maintained or WhatsApp breaks the protocol:

1. **Switch to WAHA** -- same architecture (REST API + Baileys), just different Docker image
2. **Switch to neonize** -- Python Baileys wrapper, embed in our backend directly
3. **Switch to official Business API** -- by that point, may have approval

The channel_service abstraction layer means we only change `evolution_client.py`, not the rest of the system.