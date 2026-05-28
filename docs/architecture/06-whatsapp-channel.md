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
The architecture is provider-agnostic. The channel layer should support:
- manual click-to-chat
- local bridge provider
- WhatsApp Cloud API
- BSP provider

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

## Current MVP State
- channel service API shell exists
- channel-specific queue exists
- full provider abstraction and conversation extraction remain active implementation work
