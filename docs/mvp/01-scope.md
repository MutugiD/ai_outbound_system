# MVP Scope

## Included
- separate FastAPI apps for identity, acquisition, CRM, intelligence, campaign, and channel
- dedicated Celery queues for acquisition, intelligence, campaign, and channel
- Google Maps source model for one industry and many locations
- raw profile listing and review path
- review-first promotion into CRM
- phone-first lead identity support
- provenance preservation on promoted leads

## Not Yet Included
- production-grade Playwright Google Maps scraping runtime
- full Ollama inference router extraction
- AI auto-send policy engine
- full WhatsApp provider stack
- analytics service extraction
- service-owned database schemas

## Launch Industries
- `metal_fabrication`
- `furniture_woodwork`

They are treated equally in config and job support. One source job targets exactly one industry at a time.
