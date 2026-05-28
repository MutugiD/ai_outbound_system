# Event Flows

## Acquisition to CRM
1. Operator creates Google Maps source job.
2. Acquisition service stores source and location targets.
3. Acquisition worker materializes queries and prepares scrape execution.
4. Raw profiles are stored with provenance.
5. Operator reviews profiles.
6. Acquisition service calls CRM ingestion helper.
7. CRM normalizes, deduplicates, and creates or merges leads.
8. `lead_sources` records preserve acquisition provenance.

## CRM to Intelligence
1. Promoted lead becomes eligible for enrichment.
2. Intelligence service builds lead context.
3. AI returns classification, score, digital gap, and recommended offer.
4. CRM stores the resulting enrichment output.

## CRM and Intelligence to Campaign
1. Qualified lead is enrolled into an industry-specific campaign.
2. Campaign service asks intelligence for message generation.
3. Campaign service decides eligibility and sequencing.
4. Campaign service hands prepared deliveries to channel service.

## Channel to Intelligence
1. Channel service receives inbound WhatsApp reply.
2. Conversation context is assembled.
3. Intelligence service classifies the reply and drafts the next response.
4. Channel policy determines send, draft-only, or escalation.

## Current MVP Extraction State
- acquisition queue exists
- acquisition API exists
- CRM ingestion is reusable
- dedicated intelligence/campaign/channel queues are scaffolded
- full event-bus semantics remain post-MVP
