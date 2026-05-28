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

## Implementation: Evolution API

We use [Evolution API](https://github.com/nicls0n/evolution-api) (v2.2.3) as the WhatsApp provider. It wraps Baileys (WhatsApp Web WebSocket protocol) and exposes a REST API.

### Architecture

```
WhatsApp Phone <--WS--> Evolution API (Baileys) <--REST--> Our Backend
                                                                   |
                                                              PostgreSQL
                                                              (whatsapp_sessions,
                                                               outreach_messages, replies)
```

### Outbound Flow
1. Campaign engine creates `OutreachMessage(channel=whatsapp, status=approved)`
2. Celery task picks up message from channel queue
3. Task calls Evolution API: `POST /message/sendText/{instance}`
4. Evolution API sends via WhatsApp Web protocol
5. Evolution API posts delivery webhook to `/api/v1/webhooks/whatsapp`
6. We update `OutreachMessage` status (sent → delivered → read)

### Inbound Flow
1. Contact replies on WhatsApp
2. WhatsApp servers push to Evolution API WebSocket
3. Evolution API POSTs to our webhook: `/api/v1/webhooks/whatsapp`
4. We find Contact by `whatsapp_phone`, create `Reply(channel=whatsapp)`
5. Enqueue ReplyClassifier task
6. FollowUpAutomation generates follow-up tasks

### Session Management
1. Admin creates session: `POST /api/v1/channel/whatsapp/sessions`
2. Backend creates instance in Evolution API
3. Admin scans QR code with phone
4. Session status updates to `connected`
5. Backend tracks session in `whatsapp_sessions` table

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/channel/whatsapp/health` | Check Evolution API connectivity |
| POST | `/api/v1/channel/whatsapp/sessions` | Create WhatsApp session |
| GET | `/api/v1/channel/whatsapp/sessions` | List sessions |
| GET | `/api/v1/channel/whatsapp/sessions/{id}/qr` | Get QR code for scanning |
| GET | `/api/v1/channel/whatsapp/sessions/{id}/status` | Check connection status |
| DELETE | `/api/v1/channel/whatsapp/sessions/{id}` | Disconnect + delete session |
| POST | `/api/v1/channel/whatsapp/send` | Send WhatsApp message |
| POST | `/api/v1/webhooks/whatsapp` | Inbound webhook (from Evolution API) |

### Data Model

`whatsapp_sessions` table:
- `id` (UUID PK), `team_id` (FK), `instance_name` (unique), `phone_number`, `status`, `qr_code`, `paired_at`, `last_ping`, `created_by`, `created_at`, `updated_at`

### Docker Service
```yaml
evolution-api:
  image: atendai/evolution-api:latest
  ports: ["8080:8080"]
  environment:
    - DATABASE_ENABLED=true
    - DATABASE_PROVIDER=postgresql
    - DATABASE_CONNECTION_URI=postgresql://outbound:outbound@db:5432/evolution_api
    - WEBHOOK_GLOBAL_ENABLED=true
    - WEBHOOK_GLOBAL_URL=http://api-dev:8000/api/v1/webhooks/whatsapp
    - AUTHENTICATION_TYPE=apikey
    - AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}
  volumes:
    - evolution_store:/evolution-store
```

## AI Interaction
- intelligence drafts or classifies
- campaign decides whether a send should happen
- channel decides whether it can happen safely with the selected provider

## Guardrails
No send should happen unless:
- phone is normalized
- lead is not suppressed
- lead is not opted out
- campaign eligibility passes
- provider/session health is acceptable
- daily send limit not exceeded (10-20 msgs/day during warm-up)

## Current State
- ✅ Evolution API Docker service configured
- ✅ `whatsapp_sessions` model and migration
- ✅ Evolution API HTTP client (`evolution_client.py`)
- ✅ Session management API endpoints
- ✅ Inbound webhook handler (`/api/v1/webhooks/whatsapp`)
- ✅ Outbound send endpoint
- ✅ Docker Compose with Evolution API service
- ✅ Documentation (`docs/whatsapp_evolution_api.md`)
- 🔲 Celery task wiring for campaign-triggered sends
- 🔲 Frontend WhatsApp session management UI
- 🔲 Frontend WhatsApp channel in campaign creation
- 🔲 Frontend WhatsApp column in inbox/replies view
- 🔲 Volume ramp-up throttling (10-20 msgs/day warm-up)