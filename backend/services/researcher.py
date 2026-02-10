"""AI research pipeline — blind estimation via Claude.

This module enforces the critical architectural rule: the AI NEVER sees
current market prices during the research/estimation phase.  It receives
only the question text, resolution criteria, close date, and category.
"""

import json
import logging
import re
from pathlib import Path

from anthropic import AsyncAnthropic

from config import settings
from models.schemas import AIEstimateOutput, BlindMarketInput, Confidence

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "system.txt").read_text()
_RESEARCH_TEMPLATE = (_PROMPTS_DIR / "research.txt").read_text()


class Researcher:
    """Calls Claude to produce a probability estimate for a market question.

    The prompt intentionally omits all market-price information so that
    the estimate is independent of current odds.
    """

    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # ── Model selection ──────────────────────────────────────────────

    def _select_model(
        self,
        volume: float | None = None,
        manual: bool = False,
    ) -> str:
        """Pick the Claude model based on market value or user override.

        Args:
            volume: Total market volume in USD (used for automatic
                    escalation to the high-value model).
            manual: If ``True``, always use the high-value model
                    (user-triggered deep dive).

        Returns:
            Model identifier string.
        """
        if manual:
            return settings.high_value_model
        if volume is not None and volume >= settings.high_value_volume_threshold:
            return settings.high_value_model
        return settings.default_model

    # ── Prompt construction ──────────────────────────────────────────

    def _build_blind_prompt(self, blind_input: BlindMarketInput) -> str:
        """Format the research template with ONLY non-price fields.

        This is the enforcement point for blind estimation.  The template
        receives question, resolution_criteria, close_date, and category —
        nothing else.

        Args:
            blind_input: Market metadata stripped of all price/volume data.

        Returns:
            Formatted user-message string.
        """
        return _RESEARCH_TEMPLATE.format(
            question=blind_input.question,
            resolution_criteria=blind_input.resolution_criteria or "Not specified",
            close_date=blind_input.close_date or "Not specified",
            category=blind_input.category or "General",
        )

    # ── Response parsing ─────────────────────────────────────────────

    def _parse_response(self, text: str) -> AIEstimateOutput:
        """Extract a structured ``AIEstimateOutput`` from Claude's text.

        Handles common formatting variations:
        * JSON wrapped in markdown code fences (```json ... ```)
        * Leading/trailing prose around the JSON object
        * Probability values outside the allowed [0.01, 0.99] range

        Args:
            text: Raw text response from Claude.

        Returns:
            Validated ``AIEstimateOutput``.

        Raises:
            ValueError: If no valid JSON object can be extracted.
        """
        # 1. Try to extract from markdown code fences first
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            json_str = fence_match.group(1)
        else:
            # 2. Find the outermost { ... } boundaries
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
                raise ValueError(
                    f"No JSON object found in Claude response: {text[:200]}"
                )
            json_str = text[first_brace : last_brace + 1]

        data: dict = json.loads(json_str)

        # 3. Clamp probability to [0.01, 0.99]
        raw_prob = float(data.get("probability", 0.5))
        clamped_prob = max(0.01, min(0.99, raw_prob))

        # 4. Validate / normalise confidence
        raw_confidence = str(data.get("confidence", "medium")).lower().strip()
        if raw_confidence not in {c.value for c in Confidence}:
            logger.warning(
                "Unexpected confidence value '%s', defaulting to 'medium'",
                raw_confidence,
            )
            raw_confidence = "medium"

        return AIEstimateOutput(
            reasoning=str(data.get("reasoning", "")),
            probability=clamped_prob,
            confidence=Confidence(raw_confidence),
            key_evidence=data.get("key_evidence", []),
            key_uncertainties=data.get("key_uncertainties", []),
        )

    # ── Main estimation entry point ──────────────────────────────────

    async def estimate(
        self,
        blind_input: BlindMarketInput,
        volume: float | None = None,
        manual: bool = False,
    ) -> AIEstimateOutput:
        """Run the full blind-estimation pipeline for a single market.

        1. Select the appropriate Claude model.
        2. Build a prompt that contains NO price data.
        3. Call the Claude API with web-search tooling.
        4. Handle ``pause_turn`` stop reasons (tool-use continuation).
        5. Parse and validate the structured JSON response.

        Args:
            blind_input: Market metadata (question, criteria, date, category).
            volume: Market volume in USD — used only for model selection,
                    never passed to the AI.
            manual: If ``True``, force the high-value model.

        Returns:
            Validated ``AIEstimateOutput`` with probability, reasoning, etc.
        """
        model = self._select_model(volume=volume, manual=manual)
        user_prompt = self._build_blind_prompt(blind_input)

        logger.info(
            "Researcher: estimating '%s' with model=%s",
            blind_input.question[:80],
            model,
        )

        messages: list[dict] = [{"role": "user", "content": user_prompt}]

        # Initial API call (system prompt cached for cost savings)
        response = await self.client.messages.create(
            model=model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": settings.web_search_max_uses,
                },
            ],
            messages=messages,
        )

        # Handle pause_turn (Claude may invoke web_search multiple times)
        while response.stop_reason == "pause_turn":
            logger.debug(
                "Researcher: pause_turn received, continuing conversation"
            )
            # Append the assistant's partial turn as context
            messages.append({"role": "assistant", "content": response.content})
            # Continue the conversation
            response = await self.client.messages.create(
                model=model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": settings.web_search_max_uses,
                    },
                ],
                messages=messages,
            )

        # Extract all text blocks from the final response
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)

        full_text = "\n".join(text_parts)

        if not full_text.strip():
            raise ValueError("Claude returned no text content in its response")

        logger.debug(
            "Researcher: raw response length=%d chars, model=%s",
            len(full_text),
            model,
        )

        result = self._parse_response(full_text)

        # Extract token usage for cost tracking
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)

        # Calculate estimated cost
        model_costs = {
            "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
            "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        }
        costs = model_costs.get(model, model_costs["claude-sonnet-4-5-20250929"])
        estimated_cost = (
            input_tokens * costs["input"] + output_tokens * costs["output"]
        ) / 1_000_000

        result.input_tokens = input_tokens
        result.output_tokens = output_tokens
        result.estimated_cost = round(estimated_cost, 6)

        logger.info(
            "Researcher: estimate for '%s' -> p=%.2f confidence=%s "
            "(tokens: %d in / %d out, cost: $%.4f)",
            blind_input.question[:60],
            result.probability,
            result.confidence.value,
            input_tokens,
            output_tokens,
            estimated_cost,
        )

        return result
