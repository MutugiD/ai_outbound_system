# Acquisition Operations Runbook

## Current MVP Workflow
1. Start shared infra: Postgres, Redis, MinIO.
2. Start `acquisition-api-dev`.
3. Start `acquisition-worker-dev`.
4. Create a Google Maps source with one industry and multiple locations.
5. Wait for the acquisition job to materialize query templates.
6. Review source and raw profile state.
7. Promote selected profiles into CRM.

## Notes
- Current acquisition worker prepares query templates and job state.
- Full Playwright scraping still needs to be extracted into the acquisition boundary.
- Promotion defaults to review-driven operation, not blind auto-promotion.
