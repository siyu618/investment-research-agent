"""Tests for backtest engine — metric correctness (experimental)."""

import pytest
from tools.backtest.engine import BacktestEngine, BacktestResult


def _prices(ts_code, closes, start_date="20250101"):
    return [
        {"trade_date": f"202501{d:02d}", "ts_code": ts_code, "close": c}
        for d, c in enumerate(closes, start=1)
    ]


class TestBacktestMetrics:
    # positions sized so position_value ≈ initial_capital at base price
    SHARES = 10000  # 10000 × 100 = 1,000,000

    @pytest.mark.asyncio
    async def test_flat_prices_zero_return(self):
        prices = _prices("600519.SH", [100.0] * 10)
        signals = [
            {"trade_date": f"202501{d:02d}", "positions": {"600519.SH": self.SHARES}}
            for d in range(1, 11)
        ]
        result = await BacktestEngine().run(signals, prices)
        assert isinstance(result, BacktestResult)
        assert result.experimental is True
        assert result.total_return == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_linear_gain_positive_return(self):
        # 100 → 118 = +18%
        closes = [100.0 + 2.0 * i for i in range(10)]  # 100..118
        prices = _prices("600519.SH", closes)
        signals = [
            {"trade_date": f"202501{d:02d}", "positions": {"600519.SH": self.SHARES}}
            for d in range(1, 11)
        ]
        result = await BacktestEngine().run(signals, prices)
        assert result.total_return > 0.15  # ~18%
        assert result.max_drawdown == 0.0  # monotonic up

    @pytest.mark.asyncio
    async def test_peak_then_crash_drawdown(self):
        # 100 → 150 → 100 = 33% drawdown
        closes = [100, 110, 120, 150, 140, 120, 110, 100]
        prices = _prices("600519.SH", closes)
        signals = [
            {"trade_date": f"202501{d:02d}", "positions": {"600519.SH": self.SHARES}}
            for d in range(1, len(closes) + 1)
        ]
        result = await BacktestEngine().run(signals, prices)
        # Drawdown from 150 peak to 100 trough = 33.3%
        assert result.max_drawdown == pytest.approx(0.3333, abs=1e-3)

    @pytest.mark.asyncio
    async def test_empty_signals_graceful(self):
        result = await BacktestEngine().run([], [])
        assert result.total_return == 0.0
        assert result.experimental is True

    @pytest.mark.asyncio
    async def test_cost_reduces_return(self):
        prices = _prices("600519.SH", [100.0] * 5)
        signals = [
            {"trade_date": f"202501{d:02d}", "positions": {"600519.SH": self.SHARES}}
            for d in range(1, 6)
        ]
        result = await BacktestEngine(cost_bps=50).run(signals, prices)
        # Cost eats into flat return
        assert result.total_return <= 0.0

    @pytest.mark.asyncio
    async def test_win_rate_positive_periods(self):
        # 4 closes → 4 period returns: 0%, +10%, -9%, +10% → 2/4 positive
        closes = [100, 110, 100, 110]
        prices = _prices("600519.SH", closes)
        signals = [
            {"trade_date": f"202501{d:02d}", "positions": {"600519.SH": self.SHARES}}
            for d in range(1, 5)
        ]
        result = await BacktestEngine().run(signals, prices)
        assert result.win_rate == pytest.approx(0.5, abs=0.01)
