"""Tests for controlled LLM backend — deterministic fallback + structured parse."""

import pytest
from agent.llm import LLMBackend, LLMUnavailable


class TestLLMBackendAvailability:
    def test_no_key_unavailable(self):
        backend = LLMBackend(api_key="")
        assert backend.available is False

    def test_with_key_available(self):
        backend = LLMBackend(api_key="test-key")
        assert backend.available is True


class TestLLMUnavailable:
    @pytest.mark.asyncio
    async def test_parse_raises_without_key(self):
        backend = LLMBackend(api_key="")
        with pytest.raises(LLMUnavailable):
            await backend.parse_investment_request("分析股票")

    @pytest.mark.asyncio
    async def test_polish_raises_without_key(self):
        backend = LLMBackend(api_key="")
        with pytest.raises(LLMUnavailable):
            await backend.polish_report("# Report")


class TestJSONParsing:
    def test_plain_json(self):
        result = LLMBackend._parse_json('{"risk_level": "low", "top_k": 3}')
        assert result["risk_level"] == "low"
        assert result["top_k"] == 3

    def test_code_fence_json(self):
        text = '```json\n{"objective": "growth"}\n```'
        result = LLMBackend._parse_json(text)
        assert result["objective"] == "growth"

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n{"stock_codes": ["600519.SH"]}\nDone.'
        result = LLMBackend._parse_json(text)
        assert result["stock_codes"] == ["600519.SH"]

    def test_invalid_json_raises(self):
        with pytest.raises(LLMUnavailable):
            LLMBackend._parse_json("no json here")

    def test_non_object_json_raises(self):
        with pytest.raises(LLMUnavailable):
            LLMBackend._parse_json("[1, 2, 3]")


class TestSchema:
    def test_request_schema_shape(self):
        schema = LLMBackend._request_schema()
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "risk_level" in props
        assert props["risk_level"]["enum"] == ["low", "medium", "high"]
        assert "objective" in props
        assert "stock_codes" in props


class TestPlannerLLMIntegration:
    """Planner falls back to rules when LLM is unavailable/errors."""

    @pytest.mark.asyncio
    async def test_planner_with_no_llm_uses_rules(self):
        from agent.planner import Planner

        planner = Planner(llm=None)
        plan = await planner.create_plan("分析 600519.SH")
        assert plan is not None
        assert plan.analysis_steps[0].params.get("stock_codes") == ["600519.SH"]

    @pytest.mark.asyncio
    async def test_planner_with_failing_llm_falls_back(self):
        """A broken LLM backend must not break planning."""
        from agent.planner import Planner

        class BrokenLLM:
            available = True

            async def parse_investment_request(self, requirement):
                raise LLMUnavailable("boom")

        planner = Planner(llm=BrokenLLM())
        plan = await planner.create_plan("筛选5只低风险股票")
        assert plan is not None
        assert plan.risk_preference == "low"  # rule-based result

    @pytest.mark.asyncio
    async def test_planner_with_llm_merges_fields(self):
        """LLM extraction merges with rule defaults."""
        from agent.planner import Planner

        class FakeLLM:
            available = True

            async def parse_investment_request(self, requirement):
                return {"risk_level": "high", "top_k": 3}

        planner = Planner(llm=FakeLLM())
        plan = await planner.create_plan("找股票")
        assert plan.risk_preference == "high"
        # top_k is embedded in objective text? verify via weights adjustment
        # (top_k lives in step 5 params in plan generation)
        step5 = [s for s in plan.analysis_steps if s.id == 5][0]
        assert step5.params["top_k"] == 3
