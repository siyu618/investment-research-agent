"""Deterministic metric calculation tests for fundamental analysis."""

import pytest
from strategies.fundamental_analysis.analyzer import (
    compute_roe,
    compute_revenue_growth,
    compute_profit_growth,
    compute_cashflow_quality,
    compute_debt_ratio,
    compute_gross_margin_change,
    compute_fundamental_score,
)
from tools.providers import FinancialStatement


def _make_stmt(end_date, revenue=1e9, net_profit=1e8, total_assets=2e9,
               total_liabilities=1e9, equity=1e9, ocf=8e7, fcf=6e7,
               gross_margin=0.35, eps=1.0, bvps=10.0, report_type="annual"):
    return FinancialStatement(
        ts_code="000001.SZ", end_date=end_date, report_type=report_type,
        revenue=revenue, net_profit=net_profit,
        total_assets=total_assets, total_liabilities=total_liabilities,
        equity=equity, operating_cash_flow=ocf,
        free_cash_flow=fcf, basic_eps=eps, bvps=bvps,
        gross_margin=gross_margin, roe=net_profit/equity if equity else 0,
    )


class TestComputeROE:
    def test_single_period(self):
        stmts = [_make_stmt("20241231", net_profit=100, equity=1000)]
        result = compute_roe(stmts)
        assert len(result) == 1
        assert result[0].value == 0.1  # 100/1000
        assert result[0].metric == "roe"

    def test_multiple_periods(self):
        stmts = [
            _make_stmt("20221231", net_profit=80, equity=800),
            _make_stmt("20231231", net_profit=90, equity=900),
            _make_stmt("20241231", net_profit=100, equity=1000),
        ]
        result = compute_roe(stmts)
        assert len(result) == 3
        assert result[-1].value == 0.1

    def test_skips_non_annual(self):
        stmts = [
            _make_stmt("20241231", report_type="annual"),
            _make_stmt("20240930", report_type="q3"),
        ]
        result = compute_roe(stmts)
        assert len(result) == 1

    def test_zero_equity_skipped(self):
        stmts = [_make_stmt("20241231", net_profit=100, equity=0)]
        result = compute_roe(stmts)
        assert len(result) == 0


class TestComputeRevenueGrowth:
    def test_growth_calculation(self):
        stmts = [
            _make_stmt("20221231", revenue=800),
            _make_stmt("20231231", revenue=900),
            _make_stmt("20241231", revenue=1000),
        ]
        result = compute_revenue_growth(stmts)
        assert len(result) == 2
        # (900-800)/800 = 0.125, (1000-900)/900 = 0.111
        assert result[0].value == 0.125
        assert result[1].value == pytest.approx(0.1111, rel=1e-3)

    def test_single_period_no_growth(self):
        stmts = [_make_stmt("20241231")]
        result = compute_revenue_growth(stmts)
        assert len(result) == 0

    def test_flat_revenue(self):
        stmts = [
            _make_stmt("20231231", revenue=1000),
            _make_stmt("20241231", revenue=1000),
        ]
        result = compute_revenue_growth(stmts)
        assert result[0].value == 0.0


class TestComputeProfitGrowth:
    def test_positive_growth(self):
        stmts = [
            _make_stmt("20221231", net_profit=50),
            _make_stmt("20231231", net_profit=75),
            _make_stmt("20241231", net_profit=100),
        ]
        result = compute_profit_growth(stmts)
        assert len(result) == 2
        assert result[-1].value == pytest.approx(0.3333, rel=1e-3)

    def test_negative_to_positive(self):
        stmts = [
            _make_stmt("20231231", net_profit=-100),
            _make_stmt("20241231", net_profit=50),
        ]
        result = compute_profit_growth(stmts)
        # (50 - (-100)) / abs(-100) = 150/100 = 1.5 = 150% growth from a loss base
        assert result[0].value == pytest.approx(1.5, rel=1e-3)


class TestComputeCashflowQuality:
    def test_healthy_ratio(self):
        stmts = [_make_stmt("20241231", net_profit=100, ocf=120)]
        result = compute_cashflow_quality(stmts)
        assert result[0].value == 1.2

    def test_negative_ocf(self):
        stmts = [_make_stmt("20241231", net_profit=100, ocf=-50)]
        result = compute_cashflow_quality(stmts)
        assert result[0].value == -0.5
        assert "负" in result[0].warning


class TestComputeDebtRatio:
    def test_normal_debt(self):
        stmts = [_make_stmt("20241231", total_assets=2000, total_liabilities=1000)]
        result = compute_debt_ratio(stmts)
        assert result[0].value == 0.5

    def test_high_debt_warning(self):
        stmts = [_make_stmt("20241231", total_assets=1000, total_liabilities=900)]
        result = compute_debt_ratio(stmts)
        assert result[0].value == 0.9
        assert "85%" in result[0].warning

    def test_zero_assets_skipped(self):
        stmts = [_make_stmt("20241231", total_assets=0, total_liabilities=0)]
        result = compute_debt_ratio(stmts)
        assert len(result) == 0


class TestComputeGrossMargin:
    def test_values(self):
        stmts = [
            _make_stmt("20231231", gross_margin=0.30),
            _make_stmt("20241231", gross_margin=0.35),
        ]
        result = compute_gross_margin_change(stmts)
        assert len(result) == 2
        assert result[0].value == 0.30
        assert result[1].value == 0.35


class TestFundamentalScore:
    def test_high_quality_company(self):
        roes = [type("obj", (), {"value": 0.25})()]
        rev = [type("obj", (), {"value": 0.20})()]
        profit = [type("obj", (), {"value": 0.15})()]
        cf = [type("obj", (), {"value": 1.2})()]
        debt = [type("obj", (), {"value": 0.25})()]
        margin = [type("obj", (), {"value": 0.50})()]
        score, conf, expl = compute_fundamental_score(roes, rev, profit, cf, debt, margin)
        assert score > 0.8
        assert conf > 0.5
        assert "ROE" in expl

    def test_poor_quality_company(self):
        roes = [type("obj", (), {"value": 0.02})()]
        rev = [type("obj", (), {"value": -0.10})()]
        profit = [type("obj", (), {"value": -0.15})()]
        cf = [type("obj", (), {"value": 0.1})()]
        debt = [type("obj", (), {"value": 0.90})()]
        margin = [type("obj", (), {"value": 0.03})()]
        score, conf, expl = compute_fundamental_score(roes, rev, profit, cf, debt, margin)
        assert score < 0.5
