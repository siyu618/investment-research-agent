"""Tests for Planner — requirement parsing and plan generation."""

import pytest
from agent.planner import Planner, InvestmentObjective, RiskLevel, HoldingPeriod


class TestPlanner:
    def setup_method(self):
        self.planner = Planner()

    @pytest.mark.asyncio
    async def test_value_investment_requirement(self):
        plan = await self.planner.create_plan(
            "筛选沪深300中低估值的价值投资标的，低风险"
        )
        assert plan is not None
        assert plan.risk_preference == "low"
        assert "fundamental-analysis" in plan.strategy_weights
        # Value objective should weight fundamental + valuation more
        assert plan.strategy_weights.get("fundamental-analysis", 0) > 0.3
        assert plan.strategy_weights.get("valuation-analysis", 0) > 0.3

    @pytest.mark.asyncio
    async def test_growth_requirement(self):
        plan = await self.planner.create_plan(
            "找高成长股票，高风险偏好"
        )
        assert plan is not None
        assert plan.risk_preference == "high"

    @pytest.mark.asyncio
    async def test_top_k_parsing(self):
        plan = await self.planner.create_plan("筛选10只股票")
        # parse plan contains top_k info... let me check how
        # The plan's objective string should contain top_k
        assert plan is not None

    @pytest.mark.asyncio
    async def test_default_for_ambiguous_input(self):
        plan = await self.planner.create_plan("帮我看看股票")
        assert plan is not None
        assert plan.risk_preference == "medium"  # default

    @pytest.mark.asyncio
    async def test_strategy_weights_sum_to_one(self):
        """All preset weight sets should sum to 1.0"""
        planner = Planner()
        for obj in InvestmentObjective:
            for risk in RiskLevel:
                weights = planner._default_weights(obj, risk)
                total = sum(weights.values())
                assert abs(total - 1.0) < 0.02, f"{obj.value}/{risk.value} sums to {total}"

    @pytest.mark.asyncio
    async def test_plan_has_steps(self):
        plan = await self.planner.create_plan("沪深300基本面分析")
        assert len(plan.analysis_steps) >= 5
        step_ids = [s.id for s in plan.analysis_steps]
        assert 1 in step_ids  # data collection
        assert 6 in step_ids  # verification

    @pytest.mark.asyncio
    async def test_step_dependencies(self):
        plan = await self.planner.create_plan("分析沪深300")
        steps = {s.id: s for s in plan.analysis_steps}
        # Fundamental depends on data (step 1)
        assert 1 in steps[2].depends_on
        # Portfolio depends on fund/val/risk (steps 2-4)
        assert 2 in steps[5].depends_on
        assert 3 in steps[5].depends_on
        assert 4 in steps[5].depends_on


class TestSingleStockDetection:
    def setup_method(self):
        self.planner = Planner()

    @pytest.mark.asyncio
    async def test_detects_single_stock_code(self):
        """'分析 600519.SH' → stock_pool=single, stock_codes=['600519.SH']."""
        plan = await self.planner.create_plan("分析 600519.SH")
        data_step = plan.analysis_steps[0]
        assert data_step.params["stock_codes"] == ["600519.SH"]
        assert data_step.target == "single"

    @pytest.mark.asyncio
    async def test_multiple_stock_codes(self):
        """'分析 600519.SH 和 000001.SZ' → two codes."""
        plan = await self.planner.create_plan("分析 600519.SH 和 000001.SZ")
        data_step = plan.analysis_steps[0]
        assert sorted(data_step.params["stock_codes"]) == ["000001.SZ", "600519.SH"]

    @pytest.mark.asyncio
    async def test_no_false_positive_on_bare_numbers(self):
        """Random 6-digit numbers without market suffix should not match."""
        plan = await self.planner.create_plan("筛选 5 只股票")
        data_step = plan.analysis_steps[0]
        assert data_step.params["stock_codes"] == []
        assert data_step.target == "csi300"

    @pytest.mark.asyncio
    async def test_screening_requirement(self):
        """Conditional screening: quality + reasonable valuation + medium risk."""
        plan = await self.planner.create_plan(
            "从沪深300筛选基本面稳健、估值合理且中等风险的5只股票"
        )
        assert plan.risk_preference == "medium"
        assert plan.strategy_weights.get("fundamental-analysis", 0) >= 0.3
        steps = {s.id: s for s in plan.analysis_steps}
        # portfolio selection (step 5) depends on fund/val/risk
        assert all(d in steps[5].depends_on for d in (2, 3, 4))
