# AI Response Guardrails

## MVP Rule
AI can assist with enrichment and drafting before it is trusted with fully autonomous messaging.

## Guardrails
- validate structured outputs
- do not auto-send when confidence is low
- escalate ambiguous, risky, or policy-sensitive replies
- keep channel execution separate from reply generation

## Extraction Roadmap
1. centralize AI workflows in intelligence service
2. add inference routing and structured validation
3. add shared lead/conversation context assembly
4. add channel-aware response policy
5. only then enable broader auto-response behavior
