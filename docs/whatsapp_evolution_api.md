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

Baileys reverse-engineers the WhatsApp Web binary protocol. It connects using the same WebSocket that the WhatsApp web client uses. No Puppeteer, no browser — lightweight and fast. Supports text, media, documents, locations, contacts, reactions, polls, presence, and group management. Multi-device support. Auth state persisted to file (sessions survive restarts). Pairing via QR code scan or phone number + pairing code.

### Tier 2: HTTP API Servers (best for FastAPI backend integration)

| Library | Stars | Language | Engine | Status |
|---------|-------|----------|--------|--------|
| **Evolution API** (evolution-foundation/evolution-api) | 8,500+ | TS | Baileys | Active, v2.2.3 |
| **WAHA** (devlikeapro/waha) | 6,600 | TS | 3 engines (NOWEB=Baileys, WEBJS=Puppeteer, GOWS=Go) | Active |
| **WppConnect Server** | 1,000 | TS | Puppeteer | Less active |

**We chose Evolution API** because it's Docker-ready, has webhook support, multi-session management, and a management dashboard.

---

## Architecture

```
WhatsApp Phone <--WebSocket--> Evolution API (Baileys) <--REST--> Our Backend
                                                                  |
                                                             PostgreSQL
                                                         (whatsapp_sessions,
                                                          outreach_messages,
                                                          replies, contacts)
```

### Data Flow

**Outbound**: Campaign engine → `POST /api/v1/channel/whatsapp/send` → EvolutionClient → Evolution API → WhatsApp

**Inbound**: WhatsApp → Evolution API → `POST /api/v1/webhooks/whatsapp` → Reply model + classification task

**Session pairing**: Browser → Evolution Manager UI (or API) → QR code → Phone scans → `connection.update` webhook → session status = "connected"

---

## Evolution API v2.2.3 — Critical Endpoint Changes

Evolution API v2 changed several endpoints from v1. These are **not documented clearly** in the official docs and will silently return 404 if you use the old methods.

| Endpoint | v1 Method | v2.2.3 Method | Notes |
|----------|-----------|---------------|-------|
| Create instance | POST | POST | Body MUST include `{"integration": "WHATSAPP-BAILEYS"}` |
| Connect instance | POST | **GET** | Was POST, now GET |
| Logout instance | POST | **DELETE** | Was POST, now DELETE |
| Delete instance | DELETE | DELETE | Same |
| Fetch instances | GET | GET | Same |
| Connection state | GET | GET | Same |
| Health check | GET /healthcheck | **GET /** | Root URL returns version info |
| QR code | GET /instance/qrcode | **Webhook only** | No REST endpoint; QR arrives via `qrcode.updated` webhook |
| Send text | POST /message/sendText/{instance} | POST | Same |
| Webhook set | POST (flat body) | **POST (nested)** | Body: `{"webhook": {...}}` |

### Per-Instance Webhook Configuration (REQUIRED)

The global webhook (`WEBHOOK_GLOBAL_URL`) is **not sufficient** on its own. Each instance must have its own webhook configured via:

```
POST /webhook/set/{instanceName}
{
  "webhook": {
    "url": "http://api-dev:8000/api/v1/webhooks/whatsapp",
    "enabled": true,
    "webhookByEvents": true,
    "events": [
      "APPLICATION_STARTUP",
      "QRCODE_UPDATED",
      "CONNECTION_UPDATE",
      "MESSAGES_UPSERT",
      "SEND_MESSAGE"
    ]
  }
}
```

Without this, the `QRCODE_UPDATED` event will not fire, and you'll never get the QR code. Our `EvolutionClient.configure_webhook()` method handles this automatically.

### Webhook Event Names

Evolution API v2.2.3 uses **dot notation** for event names:

| Event | Payload Key | Description |
|-------|------------|-------------|
| `connection.update` | `state` | State changes: `open`, `connecting`, `close` |
| `qrcode.updated` | `qrcode` | QR code base64 string or `{"base64": "..."}` object |
| `messages.upsert` | `data.key`, `data.message` | Inbound or outbound messages |
| `send.message` | `data.key.id`, `data.status` | Delivery receipts for sent messages |
| `message.upsert` | — | Status updates on sent messages |

### QR Code Handling

The `qrcode` field in the `qrcode.updated` webhook payload can be:
- A plain base64 string: `"data:image/png;base64,iVBOR..."`
- An object with a `base64` key: `{"base64": "2@e8Jf..."}`

Our webhook handler handles both formats.

---

## Docker Compose Setup

### Start the full dev stack

```bash
# Start everything (PostgreSQL, Redis, MinIO, Evolution API, API, workers)
docker compose --profile dev up -d

# Or start just infrastructure + Evolution API
docker compose --profile dev up -d db redis minio evolution-api
```

### Evolution API Configuration

Key environment variables in `docker-compose.yml`:

| Variable | Value | Purpose |
|----------|-------|---------|
| `DATABASE_CONNECTION_URI` | `postgresql://outbound:outbound@db:5432/evolution_api` | Evolution API's own database |
| `REDIS_URI` | `redis://redis:6379/0` | Redis for session state (use DB 0 to reduce log spam) |
| `WEBHOOK_GLOBAL_URL` | `http://api-dev:8000/api/v1/webhooks/whatsapp` | Global webhook (Docker hostname, not localhost) |
| `AUTHENTICATION_API_KEY` | `${EVOLUTION_API_KEY}` | API key for Evolution API REST calls |
| `EVOLUTION_API_URL` | `http://evolution-api:8080` | Backend → Evolution API (Docker hostname) |
| `EVOLUTION_API_KEY` | `${EVOLUTION_API_KEY}` | Backend auth key for Evolution API |

### Pre-requirements

1. Create the `evolution_api` database before first startup:
   ```bash
   docker exec ai_outbound_system-db-1 psql -U outbound -c "CREATE DATABASE evolution_api OWNER outbound;"
   ```
2. Set `EVOLUTION_API_KEY` in your `.env` file (e.g., `EVOLUTION_API_KEY=outbound-os-evolution-key`)

### Evolution Manager UI

Access at `http://localhost:8080/manager`. Login with the API key from your `.env` file.

---

## API Endpoints

### Session Management (JWT-protected)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/channel/whatsapp/health` | Check Evolution API connectivity |
| POST | `/api/v1/channel/whatsapp/sessions` | Create session (creates Evolution instance, configures webhook, triggers QR) |
| GET | `/api/v1/channel/whatsapp/sessions` | List all sessions for current team |
| GET | `/api/v1/channel/whatsapp/sessions/{id}/qr` | Get QR code for scanning |
| GET | `/api/v1/channel/whatsapp/sessions/{id}/status` | Check live connection status |
| DELETE | `/api/v1/channel/whatsapp/sessions/{id}` | Delete session (logout + delete) |
| POST | `/api/v1/channel/whatsapp/send` | Send a WhatsApp text message |

### Webhook (no auth — called by Evolution API)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/webhooks/whatsapp` | Receive all Evolution API webhook events |

### Webhook Event Processing

| Webhook Event | Action |
|---------------|--------|
| `connection.update` (state=open) | Set session status to "connected", record phone number |
| `connection.update` (state=close) | Set session status to "disconnected" |
| `qrcode.updated` | Store QR base64 in session for display |
| `messages.upsert` (fromMe=false) | Create Reply record, enqueue classification |
| `send.message` | Update OutreachMessage delivery status |

---

## Pairing a Phone (Quick Start)

1. Start the stack: `docker compose --profile dev up -d`
2. Open `http://localhost:8080/manager` and login with your API key
3. Click "Instance" to create a new WhatsApp instance
4. Click on the instance, then "Get QR Code"
5. On your spare phone: WhatsApp → Settings → Linked Devices → Link a Device
6. Scan the QR code
7. The webhook will update the session status to "connected" automatically

**Important**: If the QR code doesn't appear, the instance may be rate-limited by WhatsApp (401 status). Wait 15-30 minutes, delete the instance, create a fresh one, and try again.

---

## Troubleshooting

### Redis "disconnected" log spam

Evolution API logs `ERROR [Redis] redis disconnected` continuously. This is **cosmetic** — the Redis subscriber connection reconnects automatically and the API works fine. Using Redis DB 0 (instead of DB 2) minimizes the spam. This is a known issue in v2.2.3.

### QR code doesn't appear

1. **Per-instance webhook not configured**: Call `POST /webhook/set/{instanceName}` after creating an instance. Without this, `qrcode.updated` events won't fire.
2. **WhatsApp rate limiting (401)**: Too many connection attempts trigger rate limiting. Wait 15-30 minutes, delete the instance, create a fresh one.
3. **Check Evolution Manager UI**: Visit `http://localhost:8080/manager` and click "Get QR Code" on the instance.

### Instance shows "close" immediately after creation

This is normal — the instance starts in `close` state. Call `GET /instance/connect/{name}` to trigger the Baileys WebSocket handshake, which changes the state to `connecting` and generates a QR code.

### Webhook not receiving events

1. Check that the webhook URL uses the Docker hostname (`http://api-dev:8000/...`), NOT `localhost`
2. Verify per-instance webhook is configured: `GET /webhook/find/{instanceName}`
3. Check Evolution API container logs for `WebhookController` entries

### Phone number format

Always use international format WITHOUT `+` or spaces: `254712345678` (Kenya), `14155552671` (US). Inbound messages come with `@s.whatsapp.net` suffix — strip it.

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Account bans | Start with 10-20 msgs/day, warm up over weeks |
| Session drops | Evolution API handles reconnection; monitor connection state |
| Phone must stay online | Multi-device means phone needs internet but doesn't need WhatsApp open |
| ToS violation | Technically against WhatsApp ToS. Fine for personal/business use, risky at scale |
| No rate limit visibility | You don't know your limits until you hit them (ban) |