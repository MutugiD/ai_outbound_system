# CRM Promotion Review Runbook

## Goal
Promote reviewed source records into CRM without losing phone identity or source provenance.

## Review Checklist
- business name looks valid
- phone exists and can normalize cleanly
- category roughly matches the selected industry
- listing is not obviously closed or irrelevant
- source query and location make sense

## Promotion Behavior
- normalize raw data
- deduplicate on phone first
- create or merge company/contact/lead
- write `lead_sources` record with provenance

## CRM Identity Rules
- phone-only contacts are allowed
- `raw_phone` is preserved
- `normalized_phone` is the primary dedup key
- `whatsapp_phone` mirrors normalized phone until channel validation becomes more advanced
