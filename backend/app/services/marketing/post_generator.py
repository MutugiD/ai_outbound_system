"""LLM-powered social post generator — creates platform-specific posts from Brand Brain context.

Generates posts for Reddit, X (Twitter), LinkedIn, and Hacker News that match the
brand voice, target the right audience, and sound like a human founder — not AI.

Uses the existing LLMService for structured output with fallback to deterministic templates.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.services.ai.llm_service import LLMService

logger = logging.getLogger(__name__)

# ── Platform-specific guidelines ──────────────────────────────────────────────

PLATFORM_GUIDELINES = {
    "reddit": {
        "max_length": 4000,
        "tone": "Conversational, authentic, helpful. No selling — ask questions, share experiences.",
        "structure": "Start with a relatable hook, share the pain point, ask for input. End with a genuine question.",
        "format_tips": [
            "Use line breaks for readability",
            "Lead with the problem, not the solution",
            "End with a question that invites discussion",
            "Never say 'check out my product' — say 'has anyone dealt with this?'",
            "Be specific about the problem you're solving",
        ],
    },
    "twitter": {
        "max_length": 280,
        "tone": "Snappy, opinionated, direct. One insight per tweet.",
        "structure": "Hook → insight/takeaway → optional CTA. Keep it punchy.",
        "format_tips": [
            "One idea per tweet",
            "Use 1-2 relevant hashtags max",
            "Start with an opinion or surprising stat",
            "Thread format for longer thoughts (3-5 tweets)",
            "White space is your friend",
        ],
    },
    "linkedin": {
        "max_length": 3000,
        "tone": "Professional but personal. Founder story, lessons learned, industry insights.",
        "structure": "Hook → story/lesson → actionable takeaway → question for engagement.",
        "format_tips": [
            "Start with a bold statement or personal story",
            "Use short paragraphs (1-2 sentences)",
            "Include specific numbers or milestones",
            "End with a question that drives comments",
            "Avoid jargon — write for a smart peer, not an executive",
        ],
    },
    "hn": {
        "max_length": 4000,
        "tone": "Technical, data-driven, thoughtful. HN values substance over style.",
        "structure": "Problem → what you tried → results → ask for feedback.",
        "format_tips": [
            "Be deeply technical when relevant",
            "Share actual numbers and metrics",
            "Show your work — link to details",
            "Ask for feedback, not validation",
            "Avoid marketing language entirely",
        ],
    },
}

# ── LLM output schemas ──────────────────────────────────────────────────────

class PostVariant(BaseModel):
    """A single generated post variant."""
    hook: str = Field(description="Opening line that grabs attention")
    body: str = Field(description="Main content of the post")
    cta: str = Field(description="Call to action or engagement prompt at the end")
    full_text: str = Field(description="Complete post text, assembled from hook + body + cta")
    reasoning: str = Field(description="Why this post works for this platform and audience")


class PostGenerationOutput(BaseModel):
    """Structured output for post generation."""
    variants: list[PostVariant] = Field(description="2-3 variant posts")


# ── Post Generator ──────────────────────────────────────────────────────────

class MarketingPostGenerator:
    """Generate platform-specific social posts from Brand Brain context.

    Usage:
        generator = MarketingPostGenerator()
        result = await generator.generate_posts(
            platform="reddit",
            goal="Find early adopters for our project management tool",
            brand_brain={"product_summary": "...", "positioning": {...}, "voice_rules": [...]},
            audience_context="Found a thread about 'best tools for solo founders managing client projects'",
        )
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self._llm = llm_service or LLMService()

    async def generate_posts(
        self,
        platform: str,
        goal: str,
        brand_brain: dict[str, Any],
        audience_context: Optional[str] = None,
        variants: int = 3,
        model: str = "",
    ) -> list[dict[str, Any]]:
        """Generate platform-specific social posts.

        Args:
            platform: Target platform (reddit, twitter, linkedin, hn)
            goal: Marketing goal for this post
            brand_brain: Brand Brain dict with product_summary, positioning, voice_rules, keywords
            audience_context: Optional context from audience discovery (e.g., reddit thread title)
            variants: Number of variants to generate (1-5)
            model: LLM model to use

        Returns:
            List of post variant dicts with hook, body, cta, full_text, reasoning
        """
        platform = platform.lower()
        if platform == "x":
            platform = "twitter"

        # Use config default model if none specified
        model = model or settings.LLM_MODEL

        guidelines = PLATFORM_GUIDELINES.get(platform, PLATFORM_GUIDELINES["reddit"])
        variants = max(1, min(variants, 5))

        # Build the prompt
        product_summary = brand_brain.get("product_summary", "")
        positioning = brand_brain.get("positioning", {})
        voice_rules = brand_brain.get("voice_rules", [])
        keywords = brand_brain.get("keywords", [])

        value_prop = positioning.get("value_prop", "")
        icp = positioning.get("icp", "")

        prompt = f"""Generate {variants} distinct social media posts for {platform.upper()}.

## Product Context
{product_summary}

## Positioning
- Value proposition: {value_prop}
- Ideal customer: {icp}

## Marketing Goal
{goal}

## Brand Voice Rules
{chr(10).join(f'- {rule}' for rule in voice_rules) if voice_rules else '- Write like a human founder, not corporate marketing'}

## Platform-Specific Guidelines ({platform.upper()})
- Maximum length: {guidelines['max_length']} characters
- Tone: {guidelines['tone']}
- Structure: {guidelines['structure']}

## Audience Context
{audience_context or 'General audience interested in ' + ', '.join(keywords[:5]) if keywords else 'General audience'}

## Tips for {platform.upper()}
{chr(10).join(f'- {tip}' for tip in guidelines['format_tips'])}

## Keywords to naturally include
{', '.join(keywords[:10]) if keywords else 'Use product-specific terms'}

Generate {variants} distinct variants. Each should feel different — vary the hook angle, 
tone intensity, and approach. Make them sound like a real founder wrote them, not a marketing team.
Never use generic phrases like 'revolutionary', 'game-changer', 'leverage', or 'synergy'.
"""

        system_prompt = (
            "You are a social media strategist who writes like a human founder, not corporate marketing. "
            "You create posts that get genuine engagement because they're authentic, specific, and helpful. "
            "You avoid buzzwords, hype, and generic marketing language. "
            "Every post should make the reader feel like they're hearing from a real person who built something."
        )

        try:
            result = await self._llm.call(
                prompt=prompt,
                schema=PostGenerationOutput,
                model=model,
                task_name="marketing_post_generation",
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=2000,
            )

            posts = []
            for i, variant in enumerate(result.variants[:variants]):
                posts.append({
                    "hook": variant.hook,
                    "body": variant.body,
                    "cta": variant.cta,
                    "full_text": variant.full_text,
                    "reasoning": variant.reasoning,
                    "platform": platform,
                    "variant_index": i,
                    "model_used": model,
                })

            return posts

        except Exception as exc:
            logger.warning("LLM post generation failed, using template fallback: %s", exc)
            return self._template_fallback(platform, goal, brand_brain, audience_context, variants)

    def _template_fallback(
        self,
        platform: str,
        goal: str,
        brand_brain: dict[str, Any],
        audience_context: Optional[str],
        variants: int,
    ) -> list[dict[str, Any]]:
        """Deterministic template fallback when LLM is unavailable."""
        guidelines = PLATFORM_GUIDELINES.get(platform, PLATFORM_GUIDELINES["reddit"])
        positioning = brand_brain.get("positioning", {})
        voice_rules = brand_brain.get("voice_rules", [])
        icp = positioning.get("icp", "founders and teams")
        product = brand_brain.get("domain", "our product")

        templates = [
            {
                "hook": f"I've been building {product} and here's what I learned",
                "body": f"The biggest challenge for {icp} isn't what you'd expect. "
                        f"{audience_context or 'After talking to dozens of users, the pattern is clear.'}",
                "cta": "What's your experience with this? I'd love to hear what's worked for you.",
                "platform": platform,
                "reasoning": "Template fallback — leads with personal experience, asks for input.",
            },
            {
                "hook": f"Unpopular opinion: most {product} alternatives are solving the wrong problem",
                "body": f"Here's what {icp} actually need: {goal.lower()}. "
                        f"The tools that exist focus on features, not outcomes.",
                "cta": "Has anyone found something that actually works for this?",
                "platform": platform,
                "reasoning": "Template fallback — leads with a contrarian take, invites discussion.",
            },
            {
                "hook": f"Built something for {icp} — looking for early testers",
                "body": f"We're solving {goal.lower()}. "
                        f"{audience_context or 'The current options all miss the mark in similar ways.'}",
                "cta": "If this resonates, I'd love to hear what you're currently using and what's missing.",
                "platform": platform,
                "reasoning": "Template fallback — direct ask, positions as early-stage and learning.",
            },
        ]

        posts = []
        for i in range(min(variants, len(templates))):
            template = templates[i]
            full_text = f"{template['hook']}\n\n{template['body']}\n\n{template['cta']}"
            # Truncate to platform max length
            if len(full_text) > guidelines["max_length"]:
                full_text = full_text[:guidelines["max_length"] - 3] + "..."

            posts.append({
                **template,
                "full_text": full_text,
                "variant_index": i,
                "model_used": "template_v1",
            })

        return posts