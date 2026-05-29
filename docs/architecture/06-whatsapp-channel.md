# WhatsApp Channel

## Boundary
WhatsApp execution belongs to the channel service, not the campaign or intelligence services.

## Responsibilities
- provider abstraction
- outbound delivery execution
- inbound webhook processing
- conversation state
- delivery receipts and status updates

## Provider Strategy
The architecture is provider-agnostic. The channel layer currently supports:
- **Evolution API (Baileys)** — primary provider, connected via REST API
- manual click-to-chat (future)
- WhatsApp Cloud API (future)
- BSP provider (future)

## Implementation: Evolution API v2.2.3

We use [Evolution API](https://github.com/nicls0n/evolution-api) (v2.2.3) as the WhatsApp provider. It wraps Baileys (WhatsApp Web WebSocket protocol) and exposes a REST API.

### Architecture

```
WhatsApp Phone <--WS--> Evolution API (Baileys) <--REST--> Our Backend
                                                                  |
                                                             PostgreSQL
                                                         (whatsapp_sessions,
                                                          outreach_messages,
                                                          replies, contacts)
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `EvolutionClient` | `app/services/whatsapp/evolution_client.py` | Async HTTP client wrapping Evolution API REST endpoints |
| Session API | `app/api/whatsapp_sessions.py` | JWT-protected CRUD: create session, get QR, check status, send messages |
| Webhook handler | `app/api/whatsapp_webhook.py` | Receives events from Evolution API (no auth — called by Evolution API) |
| `WhatsAppSession` model | `app/models/whatsapp_session.py` | SQLModel table tracking instances, QR codes, connection state |
| Alembic migration | `alembic/versions/a1b2c3d4e5f6_add_whatsapp_sessions.py` | Creates `whatsapp_sessions` table |

### Per-Instance Webhook (Critical)

Each Evolution API instance **must** have its own webhook configured via `POST /webhook/set/{instanceName}`. The global webhook alone is not sufficient — `QRCODE_UPDATED` events will not fire without it.

Our `EvolutionClient.configure_webhook()` method handles this automatically when creating a session.

### Webhook Event Flow

```
Evolution API                    Our Backend
     │                               │
     ├── connection.update ─────────► Update session status (open/close/connecting)
     │   {state: "open"}             │
     │                               ├── If open: set status=connected, record phone
     │                               └── If close: set status=disconnected
     │
     ├── qrcode.updated ────────────► Store QR base64 in session
     │   {qrcode: "data:image/png;..."}  (for scanning in UI)
     │
     ├── messages.upsert ───────────► Create Reply record
     │   {fromMe: false}               │
     │                               └── Enqueue classification task
     │
     └── send.message ──────────────► Update OutreachMessage delivery status
         {key: {id: "..."}, status: "delivered"}
```

### Data Model

```sql
CREATE TABLE whatsapp_sessions (
    id            UUID PRIMARY KEY,
    team_id       UUID NOT NULL REFERENCES teams(id),
    instance_name VARCHAR(100) UNIQUE NOT NULL,
    phone_number  VARCHAR(50),
    status        VARCHAR(20) DEFAULT 'disconnected',  -- disconnected, connecting, connected
    qr_code       TEXT,           -- base64 QR for scanning
    paired_at      TIMESTAMP,
    last_ping      TIMESTAMP,
    created_by    UUID REFERENCES users(id),
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);
```

### Session Lifecycle

1. **Create**: `POST /api/v1/channel/whatsapp/sessions` creates an Evolution API instance, configures webhook, triggers connection
2. **QR Code**: QR arrives via `qrcode.updated` webhook, stored in `whatsapp_sessions.qr_code`
3. **Scan**: User scans QR with phone → `connection.update` webhook with `state=open` → status becomes `connected`
4. **Send**: `POST /api/v1/channel/whatsapp/send` sends a text message via the connected session
5. **Inbound**: Incoming messages arrive via `messages.upsert` webhook → Reply record created

### Evolution API v2.2.3 Endpoint Compatibility

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/instance/create` | POST | Body MUST include `{"integration": "WHATSAPP-BAILEYS"}` |
| `/instance/connect/{name}` | **GET** | Changed from POST in v1 |
| `/instance/logout/{name}` | **DELETE** | Changed from POST in v1 |
| `/instance/delete/{name}` | DELETE | Same as v1 |
| `/instance/fetchInstances` | GET | Returns `name` and `connectionStatus` |
| `/instance/connectionState/{name}` | GET | Returns `{"instance": {"instanceName": "...", "state": "..."}}` |
| `/` | GET | Health check (NOT `/healthcheck`) |
| `/webhook/set/{name}` | POST | Per-instance webhook (body: `{"webhook": {...}}`) |
| `/webhook/find/{name}` | GET | Check webhook config |

### Docker Configuration

Evolution API runs as a sidecar container with its own PostgreSQL database (`evolution_api`) and shares Redis with the main stack.

```yaml
# In docker-compose.yml
evolution-api:
  image: atendai/evolution-api:latest
  ports:
    - "8080:8080"
  environment:
    - DATABASE_ENABLED=true
    - DATABASE_PROVIDER=postgresql
    - DATABASE_CONNECTION_URI=postgresql://outbound:outbound@db:5432/evolution_api
    - REDIS_ENABLED=true
    - REDIS_URI=redis://redis:6379/0
    - WEBHOOK_GLOBAL_ENABLED=true
    - WEBHOOK_GLOBAL_URL=http://api-dev:8000/api/v1/webhooks/whatsapp
    - AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}
```

**Important**: The webhook URL must use the Docker hostname (`api-dev`), not `localhost`, so containers can reach each other.