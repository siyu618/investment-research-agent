# Controlled LLM Backend
#
# The LLM is used ONLY for two narrow, structured tasks:
#   1. Parse natural language → InvestmentRequest (Pydantic-validated)
#   2. Polish the final report prose
#
# It NEVER: generates a DAG, chooses tools, or does any numeric computation.
# Planning structure, skill scheduling, verification, and all math stay
# deterministic. If the LLM is unavailable (no key / network / parse failure),
# the caller falls back to the deterministic rule-based parser.

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("agent.llm")


class LLMUnavailable(Exception):
    """Raised when no LLM is configured or the call fails."""


class LLMBackend:
    """Minimal Anthropic-compatible structured-output backend.

    Configure via ANTHROPIC_API_KEY (or a custom base URL + key).
    Deterministic fallback: if anything fails, raise LLMUnavailable so the
    caller uses its rule-based path.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        api_key: str = "",
        base_url: str = "https://api.anthropic.com",
        timeout: float = 30.0,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def parse_investment_request(self, requirement: str) -> dict:
        """Natural language → structured InvestmentRequest fields.

        Returns a dict matching InvestmentRequest.__dataclass_fields__.
        Raises LLMUnavailable on any failure.
        """
        if not self.available:
            raise LLMUnavailable("ANTHROPIC_API_KEY not configured")

        schema = self._request_schema()
        prompt = (
            "Extract the user's investment request into the given JSON schema.\n"
            "Return ONLY valid JSON matching the schema. Use Chinese when the "
            "input is Chinese.\n\n"
            f"User request: {requirement}\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        text = await self._complete(prompt, max_tokens=800)
        return self._parse_json(text)

    async def polish_report(self, report_md: str) -> str:
        """Polish report prose (only wording; never numbers/structure)."""
        if not self.available:
            raise LLMUnavailable("ANTHROPIC_API_KEY not configured")

        prompt = (
            "Polish the following investment research report for clarity and "
            "professional tone. Keep ALL numbers, scores, table structure, and "
            "section headings exactly as-is. Only improve wording.\n\n"
            f"{report_md}"
        )
        return await self._complete(prompt, max_tokens=2000)

    # ─── Internal ──────────────────────────────────────────────────────

    async def _complete(self, prompt: str, max_tokens: int) -> str:
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages", headers=headers, json=body
                )
                resp.raise_for_status()
                data = resp.json()
                # Extract text from Anthropic content blocks
                blocks = data.get("content", [])
                return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            raise LLMUnavailable(str(e)) from e

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract a JSON object from LLM text (tolerates code fences)."""
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.startswith("json"):
                t = t[4:]
        # Find first { ... last }
        start = t.find("{")
        end = t.rfind("}")
        if start == -1 or end == -1:
            raise LLMUnavailable("No JSON object in LLM response")
        try:
            data = json.loads(t[start : end + 1])
        except json.JSONDecodeError as e:
            raise LLMUnavailable(f"Invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise LLMUnavailable("LLM response is not a JSON object")
        return data

    @staticmethod
    def _request_schema() -> dict:
        """JSON Schema for InvestmentRequest extraction."""
        return {
            "type": "object",
            "properties": {
                "stock_pool": {"type": "string", "description": "csi300/sse50/all"},
                "stock_codes": {"type": "array", "items": {"type": "string"},
                                "description": "explicit ts_codes like 600519.SH"},
                "objective": {"type": "string", "enum": ["value", "growth", "quality",
                                                         "momentum", "income", "mixed"]},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "holding_period": {"type": "string", "enum": ["short", "medium", "long"]},
                "top_k": {"type": "integer"},
                "constraints": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        }
