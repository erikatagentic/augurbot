"""AI research pipeline — blind estimation via Claude.

This module enforces the critical architectural rule: the AI NEVER sees
current market prices during the research/estimation phase.  It receives
only the question text, resolution criteria, close date, and category.
"""

import asyncio
import json
import logging
import math
import re
from pathlib import Path

from anthropic import AsyncAnthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from config import settings
from models.schemas import AIEstimateOutput, BlindMarketInput, Confidence

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "system.txt").read_text()
_RESEARCH_TEMPLATE = (_PROMPTS_DIR / "research.txt").read_text()

# Category-specific prompts (extensible — add politics, economics, etc.)
_SYSTEM_PROMPT_SPORTS = (_PROMPTS_DIR / "system_sports.txt").read_text()
_RESEARCH_TEMPLATE_SPORTS = (_PROMPTS_DIR / "research_sports.txt").read_text()

# Registry: category name -> (system_prompt, research_template)
_CATEGORY_PROMPTS: dict[str, tuple[str, str]] = {
    "sports": (_SYSTEM_PROMPT_SPORTS, _RESEARCH_TEMPLATE_SPORTS),
    # Future: "politics": (_SYSTEM_PROMPT_POLITICS, _RESEARCH_TEMPLATE_POLITICS),
}


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
        use_premium: bool = False,
    ) -> str:
        """Pick the Claude model based on market value or user override.

        Args:
            volume: Total market volume in USD (used for automatic
                    escalation to the high-value model).
            manual: If ``True``, always use the high-value model
                    (user-triggered deep dive).
            use_premium: If ``True``, always use the high-value model
                         (set via Settings UI toggle).

        Returns:
            Model identifier string.
        """
        if manual or use_premium:
            return settings.high_value_model
        if volume is not None and volume >= settings.high_value_volume_threshold:
            return settings.high_value_model
        return settings.default_model

    # ── Prompt construction ──────────────────────────────────────────

    def _get_prompts(
        self, blind_input: BlindMarketInput,
    ) -> tuple[str, str]:
        """Select system prompt and research template based on category.

        Uses the category-specific prompt registry if a match exists,
        otherwise falls back to the generic prompts.
        """
        category = (blind_input.category or "").lower()
        if category in _CATEGORY_PROMPTS:
            return _CATEGORY_PROMPTS[category]
        return _SYSTEM_PROMPT, _RESEARCH_TEMPLATE

    def _build_blind_prompt(self, blind_input: BlindMarketInput) -> str:
        """Format the research template with ONLY non-price fields.

        This is the enforcement point for blind estimation.  The template
        receives question, resolution_criteria, close_date, and category —
        nothing else.  Category-specific templates may include additional
        non-price fields like sport_type and calibration_feedback.

        Args:
            blind_input: Market metadata stripped of all price/volume data.

        Returns:
            Formatted user-message string.
        """
        _, template = self._get_prompts(blind_input)

        # Sports-specific template uses different fields
        category = (blind_input.category or "").lower()
        if category in _CATEGORY_PROMPTS:
            calibration_section = ""
            if blind_input.calibration_feedback:
                calibration_section = (
                    "YOUR HISTORICAL PERFORMANCE (use this to calibrate):\n"
                    + blind_input.calibration_feedback
                )
            return template.format(
                question=blind_input.question,
                resolution_criteria=blind_input.resolution_criteria or "Not specified",
                close_date=blind_input.close_date or "Not specified",
                sport_type=blind_input.sport_type or "Unknown",
                calibration_section=calibration_section,
            )

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

        # 3. Validate and clamp probability to [0.01, 0.99]
        raw_prob = float(data.get("probability", 0.5))
        if not math.isfinite(raw_prob):
            logger.warning(
                "Non-finite probability value: %s — defaulting to 0.5", raw_prob
            )
            raw_prob = 0.5
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

    # ── Pre-screening with Haiku ──────────────────────────────────────

    async def screen(self, blind_input: BlindMarketInput) -> bool:
        """Quick Haiku pre-screen: is this market worth full research?

        Costs ~$0.001 per call. Returns True if the market should proceed
        to full Sonnet estimation, False to skip it.
        """
        prompt = (
            f"You are a prediction market analyst. Quickly decide if this market "
            f"is worth spending time researching.\n\n"
            f"GOOD markets (say YES):\n"
            f"- Game outcomes: 'Will Team X beat Team Y?'\n"
            f"- Selection/participation: 'Will Player X be selected for Event Y?'\n"
            f"- Awards and voting: MVP, All-Star, draft picks\n"
            f"- Any clear yes/no question with publicly available data to research\n"
            f"- Major leagues: NBA, NFL, MLB, NHL, college, soccer, UFC, tennis\n\n"
            f"BAD markets (say NO):\n"
            f"- Individual stat lines: 'Will Player X score 30+ points?'\n"
            f"- Over/under on specific player stats (points, rebounds, assists)\n"
            f"- Markets with no public data or unclear resolution criteria\n"
            f"- Already-decided events\n\n"
            f"MARKET: {blind_input.question}\n"
            f"CLOSE DATE: {blind_input.close_date or 'Unknown'}\n"
            f"SPORT: {blind_input.sport_type or 'Unknown'}\n\n"
            f"Reply with ONLY 'YES' or 'NO' (one word)."
        )

        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.content[0].text.strip().upper()
            return answer.startswith("YES")
        except Exception:
            logger.debug("Researcher: Haiku screen failed, defaulting to YES")
            return True  # fail-open: research the market if screening fails

    # ── Main estimation entry point ──────────────────────────────────

    async def estimate(
        self,
        blind_input: BlindMarketInput,
        volume: float | None = None,
        manual: bool = False,
        use_premium: bool = False,
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
            use_premium: If ``True``, force the high-value model
                         (set via Settings UI toggle).

        Returns:
            Validated ``AIEstimateOutput`` with probability, reasoning, etc.
        """
        model = self._select_model(volume=volume, manual=manual, use_premium=use_premium)
        user_prompt = self._build_blind_prompt(blind_input)
        system_prompt, _ = self._get_prompts(blind_input)

        logger.info(
            "Researcher: estimating '%s' with model=%s category=%s",
            blind_input.question[:80],
            model,
            blind_input.category or "general",
        )

        messages: list[dict] = [{"role": "user", "content": user_prompt}]
        system_block = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        tools_block = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": settings.web_search_max_uses,
            },
        ]

        # Initial API call (system prompt cached for cost savings)
        response = await self.client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_block,
            tools=tools_block,
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
                system=system_block,
                tools=tools_block,
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
            "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
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

    # ── Batch estimation ──────────────────────────────────────────────

    # Batch pricing: 50% off tokens (web search NOT discounted)
    _BATCH_COSTS = {
        "claude-haiku-4-5-20251001": {"input": 0.40, "output": 2.0},
        "claude-sonnet-4-5-20250929": {"input": 1.50, "output": 7.50},
        "claude-opus-4-6": {"input": 7.50, "output": 37.50},
    }

    async def estimate_batch(
        self,
        items: list[tuple[str, BlindMarketInput]],
        use_premium: bool = False,
        volume_map: dict[str, float] | None = None,
        poll_interval: int = 30,
        timeout_seconds: int = 7200,
    ) -> dict[str, AIEstimateOutput]:
        """Submit multiple markets as a single Anthropic batch.

        Args:
            items: List of ``(custom_id, blind_input)`` tuples.
            use_premium: If True, use Opus for all estimates.
            volume_map: Optional ``{custom_id: volume}`` for model selection.
            poll_interval: Seconds between status checks.
            timeout_seconds: Max wait time before giving up (default 2h).

        Returns:
            Dict mapping ``custom_id`` to ``AIEstimateOutput`` for
            successfully completed requests.
        """
        if not items:
            return {}

        # Select model (same for all items in batch)
        sample_volume = None
        if volume_map:
            vols = [v for v in volume_map.values() if v is not None]
            sample_volume = max(vols) if vols else None
        model = self._select_model(
            volume=sample_volume, use_premium=use_premium,
        )

        logger.info(
            "Researcher: creating batch with %d items, model=%s",
            len(items), model,
        )

        # Build batch requests
        requests: list[Request] = []
        for custom_id, blind_input in items:
            system_prompt, _ = self._get_prompts(blind_input)
            user_prompt = self._build_blind_prompt(blind_input)

            requests.append(
                Request(
                    custom_id=custom_id,
                    params=MessageCreateParamsNonStreaming(
                        model=model,
                        max_tokens=4096,
                        system=[
                            {
                                "type": "text",
                                "text": system_prompt,
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
                        messages=[{"role": "user", "content": user_prompt}],
                    ),
                )
            )

        # Submit batch
        batch = await self.client.messages.batches.create(requests=requests)
        batch_id = batch.id
        logger.info("Researcher: batch %s created (%d requests)", batch_id, len(requests))

        # Poll for completion
        elapsed = 0
        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            batch = await self.client.messages.batches.retrieve(batch_id)
            if batch.processing_status == "ended":
                logger.info(
                    "Researcher: batch %s ended — succeeded=%d errored=%d expired=%d",
                    batch_id,
                    batch.request_counts.succeeded,
                    batch.request_counts.errored,
                    batch.request_counts.expired,
                )
                break

            logger.debug(
                "Researcher: batch %s processing — %d succeeded, %d in progress (%ds elapsed)",
                batch_id,
                batch.request_counts.succeeded,
                batch.request_counts.processing,
                elapsed,
            )
        else:
            # Timeout — cancel and return empty
            logger.warning(
                "Researcher: batch %s timed out after %ds, cancelling",
                batch_id, timeout_seconds,
            )
            try:
                await self.client.messages.batches.cancel(batch_id)
            except Exception:
                pass
            return {}

        # Collect results
        results: dict[str, AIEstimateOutput] = {}
        batch_costs = self._BATCH_COSTS.get(
            model, self._BATCH_COSTS["claude-sonnet-4-5-20250929"]
        )

        async for entry in self.client.messages.batches.results(batch_id):
            if entry.result.type != "succeeded":
                logger.warning(
                    "Researcher: batch item %s status=%s",
                    entry.custom_id, entry.result.type,
                )
                continue

            message = entry.result.message

            # Extract text blocks
            text_parts = [
                block.text for block in message.content if hasattr(block, "text")
            ]
            full_text = "\n".join(text_parts)

            if not full_text.strip():
                logger.warning(
                    "Researcher: batch item %s returned no text", entry.custom_id,
                )
                continue

            try:
                result = self._parse_response(full_text)
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Researcher: batch item %s parse error: %s",
                    entry.custom_id, exc,
                )
                continue

            # Token usage + batch-discounted cost
            usage = message.usage
            input_tokens = getattr(usage, "input_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0)
            estimated_cost = (
                input_tokens * batch_costs["input"]
                + output_tokens * batch_costs["output"]
            ) / 1_000_000

            result.input_tokens = input_tokens
            result.output_tokens = output_tokens
            result.estimated_cost = round(estimated_cost, 6)

            results[entry.custom_id] = result

        logger.info(
            "Researcher: batch %s — %d/%d results parsed successfully",
            batch_id, len(results), len(items),
        )

        return results
