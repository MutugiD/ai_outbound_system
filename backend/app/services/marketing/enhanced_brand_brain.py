"""Enhanced Brand Brain — derives marketing profile from website + LLM refinement.

Takes the lightweight keyword extraction from brand_brain.py and enhances it with
LLM-generated positioning, ICP, and voice rules that actually reflect the product.
"""

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.services.ai.llm_service import LLMService
from app.services.marketing.brand_brain import derive_brand_brain as _derive_brand_brain_basic

logger = logging.getLogger(__name__)


class PositioningOutput(BaseModel):
    """Structured output for LLM-generated positioning."""
    value_proposition: str = Field(
        description="Clear 1-sentence value prop: who it's for, the pain, and the outcome"
    )
    ideal_customer_profile: str = Field(
        description="Detailed ICP: role, company size, industry, pain points, goals"
    )
    tone_guidelines: list[str] = Field(
        description="5-7 specific tone/voice rules tailored to this product's audience"
    )
    differentiators: list[str] = Field(
        description="3-5 key differentiators from competitors"
    )
    product_category: str = Field(
        description="Category label (e.g., 'project management', 'email marketing', 'dev tools')"
    )
    tagline_suggestions: list[str] = Field(
        description="3-5 short tagline options"
    )


class EnhancedBrandBrain:
    """Derive a rich Brand Brain from a website, enhanced with LLM.

    Falls back to basic keyword extraction if LLM is unavailable.
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self._llm = llm_service or LLMService()

    async def derive(
        self,
        website_url: str,
        additional_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """Derive an enhanced Brand Brain from a website URL.

        Args:
            website_url: The product website to analyze
            additional_context: Optional extra context about the product (from user input)

        Returns:
            Brand Brain dict with product_summary, positioning, voice_rules, keywords,
            differentiators, taglines, etc.
        """
        # Step 1: Get basic brand brain from website crawl
        basic = await _derive_brand_brain_basic(website_url)

        # Step 2: Enhance with LLM
        try:
            enhanced = await self._enhance_with_llm(basic, additional_context)
            return enhanced
        except Exception as exc:
            logger.warning("LLM enhancement failed, returning basic brand brain: %s", exc)
            return basic

    async def _enhance_with_llm(
        self,
        basic_brain: dict[str, Any],
        additional_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """Use LLM to enhance the basic Brand Brain with better positioning and voice."""
        product_summary = basic_brain.get("product_summary", "")
        keywords = basic_brain.get("keywords", [])
        basic_voice = basic_brain.get("voice_rules", [])
        domain = basic_brain.get("domain", "")

        prompt = f"""Analyze this product and create a detailed marketing profile.

## Product Website
{domain}

## Crawl Summary
{product_summary}

## Extracted Keywords
{', '.join(keywords[:15]) if keywords else 'No keywords extracted'}

## Additional Context
{additional_context or 'None provided'}

Create a precise marketing profile with:
1. A compelling value proposition that clarifies who it's for, what pain it solves, and what outcome they get
2. A detailed ideal customer profile (ICP)
3. Voice and tone guidelines that make the content sound like a real founder, not AI
4. Key differentiators from competitors
5. Short tagline options

The value prop should be specific and concrete — avoid generic phrases like "streamline your workflow" or "empower your team".
The ICP should include role, company size, industry, and specific pain points.
The voice rules should prevent robotic, marketing-speak content."""

        system_prompt = (
            "You are a product positioning expert who creates sharp, specific marketing profiles. "
            "You never use buzzwords like 'revolutionary', 'game-changer', or 'leverage'. "
            "You focus on concrete specifics: who the product is for, what specific pain they feel, "
            "and what measurable outcome they get."
        )

        result = await self._llm.call(
            prompt=prompt,
            schema=PositioningOutput,
            model=settings.LLM_MODEL,
            task_name="brand_brain_enhancement",
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=1500,
        )

        # Merge LLM results with basic Brand Brain
        enhanced = dict(basic_brain)  # Start with basic crawl data
        enhanced["positioning"] = {
            "value_prop": result.value_proposition,
            "icp": result.ideal_customer_profile,
        }
        enhanced["voice_rules"] = result.tone_guidelines
        enhanced["differentiators"] = result.differentiators
        enhanced["product_category"] = result.product_category
        enhanced["tagline_suggestions"] = result.tagline_suggestions
        enhanced["enhancement_model"] = settings.LLM_MODEL

        return enhanced