"""LLM service layer — structured output generation with model routing, retries, and cost tracking.

Supports:
  - Ollama (default): Local/self-hosted models via OpenAI-compatible API
  - OpenAI: GPT-4o, GPT-4o-mini for complex tasks
  - Anthropic (fallback): Claude models when OpenAI is unavailable
  - Structured JSON output validated against Pydantic schemas
  - Retry on validation failure with schema correction
  - Cost tracking per task per day (cloud providers only)
"""

import json
import logging
from datetime import date
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

# ── Cost per 1K tokens (approximate, in USD) — cloud providers only ──────────

MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    # Ollama models are free (local inference)
}


class LLMService:
    """Async LLM service with structured output, model routing, and cost tracking.

    Provider selection via settings.LLM_PROVIDER:
      - "ollama": Uses Ollama's OpenAI-compatible API (default, free/local)
      - "openai": Uses OpenAI's API (requires OPENAI_API_KEY)
      - "anthropic": Uses Anthropic's API (requires ANTHROPIC_API_KEY)

    For Ollama, settings.LLM_BASE_URL and settings.LLM_MODEL control the endpoint
    and model. Defaults: http://localhost:11434/v1 and qwen3:8b.
    """

    def __init__(self) -> None:
        self._openai_client = None
        self._anthropic_client = None

    @property
    def provider(self) -> str:
        """Active LLM provider (from settings)."""
        return settings.LLM_PROVIDER.lower()

    @property
    def default_model(self) -> str:
        """Default model for the active provider."""
        if self.provider == "ollama":
            return settings.LLM_MODEL
        elif self.provider == "anthropic":
            return "claude-3-5-sonnet-20241022"
        else:  # openai
            return "gpt-4o-mini"

    # ── Client lazy-initialization ──────────────────────────────────────────

    def _get_openai_compatible_client(self):
        """Lazy-init an OpenAI-compatible async client.

        Works for both Ollama (http://localhost:11434/v1) and OpenAI
        (https://api.openai.com/v1). The base_url and api_key are
        selected based on the active provider.
        """
        if self._openai_client is not None:
            return self._openai_client

        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package is required: pip install openai>=1.0.0")

        if self.provider == "ollama":
            # Ollama serves an OpenAI-compatible API — no real API key needed,
            # but the SDK requires *something* in the field.
            self._openai_client = AsyncOpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key="ollama",  # Ollama ignores API keys
            )
        else:
            # OpenAI — use their official endpoint and real key
            base_url = settings.LLM_BASE_URL or "https://api.openai.com/v1"
            self._openai_client = AsyncOpenAI(
                base_url=base_url,
                api_key=settings.OPENAI_API_KEY,
            )
        return self._openai_client

    def _get_anthropic_client(self):
        """Lazy-init the Anthropic async client."""
        if self._anthropic_client is None:
            try:
                import anthropic
                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=settings.ANTHROPIC_API_KEY,
                )
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
            Model to use. Defaults to provider's default model.
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
        model = model or self.default_model
        fallback_models = fallback_models or []
        all_models = [model] + fallback_models

        last_error: Optional[Exception] = None

        for current_model in all_models:
            for attempt in range(3):  # MAX_RETRIES = 2 → 3 attempts
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
                    # Track cost (no-op for Ollama)
                    self._track_cost(task_name, current_model, result)
                    return result
                except ValidationError as exc:
                    logger.warning(
                        "Validation error on model %s attempt %d: %s",
                        current_model, attempt, exc,
                    )
                    last_error = exc
                    if attempt < 2:  # retry with schema correction
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

        if model.startswith(("gpt", "o1", "o3")) or self.provider == "ollama":
            # Ollama uses the OpenAI-compatible API, so all Ollama models
            # go through the OpenAI client with custom base_url
            return await self._call_openai_compatible(
                model, prompt, schema, schema_str, system_prompt, temperature, max_tokens
            )
        elif model.startswith("claude"):
            return await self._call_anthropic(
                model, prompt, schema, schema_str, system_prompt, temperature, max_tokens
            )
        else:
            raise ValueError(f"Unsupported model: {model}")

    async def _call_openai_compatible(
        self,
        model: str,
        prompt: str,
        schema: Type[BaseModel],
        schema_str: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> BaseModel:
        """Call OpenAI-compatible API (works for both OpenAI and Ollama)."""
        client = self._get_openai_compatible_client()

        # For Ollama, check that the provider is set up
        if self.provider == "ollama" and not settings.LLM_BASE_URL:
            raise ValueError("LLM_BASE_URL not configured for Ollama")

        # For OpenAI, check API key
        if self.provider == "openai" and not settings.OPENAI_API_KEY:
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

        # Ollama models may not support response_format=json_object — only use it for OpenAI
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.provider != "ollama":
            kwargs["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        if not content:
            # Ollama models sometimes return empty content with finish_reason="length"
            # Try again with higher max_tokens
            if response.choices[0].finish_reason == "length":
                kwargs["max_tokens"] = max_tokens * 2
                response = await client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
            if not content:
                raise ValueError(f"Empty response from model {model} (finish_reason={response.choices[0].finish_reason})")

        # Strip markdown code blocks if present (common with local models)
        content = content.strip()
        if content.startswith("```"):
            # Remove opening ```json or ``` and closing ```
            first_line_end = content.find("\n")
            if first_line_end != -1:
                content = content[first_line_end + 1:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

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

    _daily_costs: dict[str, dict[date, float]] = {}

    def _track_cost(self, task_name: str, model: str, result: BaseModel) -> None:
        """Track estimated cost for an LLM call. No-op for Ollama (free)."""
        # Skip cost tracking for Ollama models (local = free)
        if self.provider == "ollama":
            logger.debug("Ollama call: task=%s model=%s (no cost — local inference)", task_name, model)
            return

        usage = getattr(result, "_llm_usage", None)
        if not usage:
            return

        costs = MODEL_COSTS.get(model, {"input": 0.001, "output": 0.002})
        input_cost = (usage.get("prompt_tokens", 0) / 1000) * costs["input"]
        output_cost = (usage.get("completion_tokens", 0) / 1000) * costs["output"]
        total_cost = input_cost + output_cost

        today = date.today()
        if task_name not in self._daily_costs:
            self._daily_costs[task_name] = {}
        self._daily_costs[task_name][today] = self._daily_costs[task_name].get(today, 0.0) + total_cost

        logger.info(
            "LLM cost: task=%s model=%s input=%d output=%d cost=$%.6f",
            task_name, model,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            total_cost,
        )

    @staticmethod
    def get_daily_costs(task_name: Optional[str] = None) -> dict:
        """Return cost tracking data."""
        costs = LLMService._daily_costs
        if task_name:
            return costs.get(task_name, {})
        return costs