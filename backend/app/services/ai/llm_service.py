"""LLM service layer — structured output generation with model routing, retries, and cost tracking.

Supports:
  - OpenAI (primary): GPT-4o for complex tasks, GPT-4o-mini for bulk classification
  - Anthropic (fallback): Claude models when OpenAI is unavailable
  - Structured JSON output validated against Pydantic schemas
  - Retry on validation failure with schema correction
  - Cost tracking per task per day
"""

import json
import logging
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

# ── Cost per 1K tokens (approximate, in USD) ─────────────────────────────────

MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
}

DEFAULT_MODEL = "gpt-4o-mini"
COMPLEX_TASK_MODEL = "gpt-4o"

FALLBACK_MODELS = {
    "gpt-4o": ["gpt-4o-mini", "claude-3-5-sonnet-20241022"],
    "gpt-4o-mini": ["gpt-4o", "claude-3-5-sonnet-20241022"],
    "gpt-4-turbo": ["gpt-4o", "claude-3-5-sonnet-20241022"],
}

MAX_RETRIES = 2

# ── In-memory cost tracker (per day) ─────────────────────────────────────────

_daily_costs: dict[str, dict[date, float]] = {}  # {task_name: {date: cost_usd}}


class LLMService:
    """Async LLM service with structured output, model routing, and cost tracking."""

    def __init__(self) -> None:
        self._openai_client = None
        self._anthropic_client = None

    # ── Client lazy-initialization ──────────────────────────────────────────

    def _get_openai_client(self):
        """Lazy-init the OpenAI async client."""
        if self._openai_client is None:
            try:
                from openai import AsyncOpenAI

                self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            except ImportError:
                raise ImportError("openai package is required: pip install openai>=1.0.0")
        return self._openai_client

    def _get_anthropic_client(self):
        """Lazy-init the Anthropic async client."""
        if self._anthropic_client is None:
            try:
                import anthropic

                self._anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            except ImportError:
                raise ImportError("anthropic package is required: pip install anthropic>=0.25.0")
        return self._anthropic_client

    # ── Public API ──────────────────────────────────────────────────────────

    async def call(
        self,
        prompt: str,
        schema: Type[BaseModel],
        model: Optional[str] = None,
        fallback_models: Optional[list[str]] = None,
        task_name: str = "default",
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> BaseModel:
        """Call an LLM with structured output validation against a Pydantic schema.

        Parameters
        ----------
        prompt : str
            The user prompt to send.
        schema : Type[BaseModel]
            Pydantic model class to validate the response against.
        model : str | None
            Model to use.  Defaults to GPT-4o-mini.
        fallback_models : list[str] | None
            Ordered list of models to try if the primary fails.
        task_name : str
            Label for cost tracking.
        system_prompt : str | None
            Optional system prompt.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Max tokens in the response.

        Returns
        -------
        BaseModel
            Validated instance of ``schema``.

        Raises
        ------
        ValueError
            If all models and retries fail.
        """
        model = model or DEFAULT_MODEL
        fallback_models = fallback_models or FALLBACK_MODELS.get(model, [])
        all_models = [model] + fallback_models

        last_error: Optional[Exception] = None

        for current_model in all_models:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    result = await self._call_model(
                        model=current_model,
                        prompt=prompt,
                        schema=schema,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        attempt=attempt,
                    )
                    # Track cost
                    self._track_cost(task_name, current_model, result)
                    return result
                except ValidationError as exc:
                    logger.warning(
                        "Validation error on model %s attempt %d: %s",
                        current_model,
                        attempt,
                        exc,
                    )
                    last_error = exc
                    if attempt < MAX_RETRIES:
                        # Re-prompt with schema correction
                        prompt = self._add_schema_correction(prompt, schema, str(exc))
                    continue
                except Exception as exc:
                    logger.warning("Model %s failed on attempt %d: %s", current_model, attempt, exc)
                    last_error = exc
                    break  # try next model

        raise ValueError(f"All LLM models failed for task '{task_name}': {last_error}")

    # ── Model-specific calls ───────────────────────────────────────────────

    async def _call_model(
        self,
        model: str,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        attempt: int,
    ) -> BaseModel:
        """Call a specific model and validate the response."""
        schema_json = schema.model_json_schema()
        schema_str = json.dumps(schema_json, indent=2)

        if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
            return await self._call_openai(model, prompt, schema, schema_str, system_prompt, temperature, max_tokens)
        elif model.startswith("claude"):
            return await self._call_anthropic(model, prompt, schema, schema_str, system_prompt, temperature, max_tokens)
        else:
            raise ValueError(f"Unsupported model: {model}")

    async def _call_openai(
        self,
        model: str,
        prompt: str,
        schema: Type[BaseModel],
        schema_str: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> BaseModel:
        """Call OpenAI API with structured output."""
        client = self._get_openai_client()

        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Inject schema instruction
        schema_instruction = (
            f"\n\nYou MUST respond with a JSON object matching this exact schema:\n"
            f"{schema_str}\n\n"
            f"Do NOT include any text outside the JSON object. Respond with valid JSON only."
        )

        messages.append({"role": "user", "content": prompt + schema_instruction})

        response_format = {"type": "json_object"}

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError(f"Empty response from OpenAI model {model}")

        # Parse JSON and validate against schema
        raw = json.loads(content)
        validated = schema.model_validate(raw)

        # Store usage for cost tracking
        validated._llm_usage = {
            "model": model,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        }

        return validated

    async def _call_anthropic(
        self,
        model: str,
        prompt: str,
        schema: Type[BaseModel],
        schema_str: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> BaseModel:
        """Call Anthropic API with structured output."""
        client = self._get_anthropic_client()

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        schema_instruction = (
            f"\n\nYou MUST respond with a JSON object matching this exact schema:\n"
            f"{schema_str}\n\n"
            f"Do NOT include any text outside the JSON object. Respond with valid JSON only."
        )

        full_system = (system_prompt or "") + "\n\nYou are a helpful assistant that responds in structured JSON format."
        messages = [{"role": "user", "content": prompt + schema_instruction}]

        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=full_system,
            messages=messages,
        )

        content = response.content[0].text if response.content else ""
        if not content:
            raise ValueError(f"Empty response from Anthropic model {model}")

        # Anthropic may wrap JSON in markdown code blocks
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = (
                content.split("```")[-2].strip() if content.count("```") >= 2 else content.split("```")[-1].strip()
            )

        raw = json.loads(content)
        validated = schema.model_validate(raw)

        validated._llm_usage = {
            "model": model,
            "prompt_tokens": response.usage.input_tokens if response.usage else 0,
            "completion_tokens": response.usage.output_tokens if response.usage else 0,
        }

        return validated

    # ── Schema correction for retries ──────────────────────────────────────

    @staticmethod
    def _add_schema_correction(
        prompt: str,
        schema: Type[BaseModel],
        validation_error: str,
    ) -> str:
        """Append a correction instruction to the prompt on validation failure."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        return (
            f"{prompt}\n\n"
            f"PREVIOUS RESPONSE FAILED VALIDATION:\n{validation_error}\n\n"
            f"Please correct your response to match this schema exactly:\n{schema_json}\n"
            f"You MUST respond with valid JSON matching this schema."
        )

    # ── Cost tracking ──────────────────────────────────────────────────────

    def _track_cost(self, task_name: str, model: str, result: BaseModel) -> None:
        """Track estimated cost for an LLM call."""
        usage = getattr(result, "_llm_usage", None)
        if not usage:
            return

        costs = MODEL_COSTS.get(model, {"input": 0.001, "output": 0.002})
        input_cost = (usage.get("prompt_tokens", 0) / 1000) * costs["input"]
        output_cost = (usage.get("completion_tokens", 0) / 1000) * costs["output"]
        total_cost = input_cost + output_cost

        today = date.today()
        if task_name not in _daily_costs:
            _daily_costs[task_name] = {}
        _daily_costs[task_name][today] = _daily_costs[task_name].get(today, 0.0) + total_cost

        logger.info(
            "LLM cost: task=%s model=%s input=%d output=%d cost=$%.6f",
            task_name,
            model,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            total_cost,
        )

    @staticmethod
    def get_daily_costs(task_name: Optional[str] = None) -> dict:
        """Return cost tracking data."""
        if task_name:
            return _daily_costs.get(task_name, {})
        return _daily_costs
