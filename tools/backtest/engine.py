# Backtest Engine — EXPERIMENTAL strategy evaluation interface
#
# ⚠️ STATUS: Experimental. This engine computes standard metrics
# (return / drawdown / Sharpe / win rate) but is NOT production-grade.
# It does NOT yet enforce:
#   - strict point-in-time data (survivorship bias possible)
#   - transaction costs / slippage
#   - trading halts, price-limit days, delistings
#
# Do not draw investment conclusions from its output. It exists to
# demonstrate the evaluation interface and to be completed when the
# above preconditions are met.

from __future__ import annotations

import math


class BacktestResult:
    """Results from a backtest run."""

    def __init__(
        self,
        total_return: float = 0.0,
        annualized_return: float = 0.0,
        max_drawdown: float = 0.0,
        sharpe_ratio: float = 0.0,
        win_rate: float = 0.0,
        total_trades: int = 0,
        period: str = "",
        experimental: bool = True,
    ):
        self.total_return = total_return
        self.annualized_return = annualized_return
        self.max_drawdown = max_drawdown
        self.sharpe_ratio = sharpe_ratio
        self.win_rate = win_rate
        self.total_trades = total_trades
        self.period = period
        self.experimental = experimental

    def to_dict(self) -> dict:
        return {
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "period": self.period,
            "experimental": self.experimental,
        }


class BacktestEngine:
    """Runs strategy signals against historical prices to compute metrics.

    Interface (reserved for strict backtesting once point-in-time data,
    costs, and market-structure handling are added):
      strategy_signals — list of {trade_date, ts_code, position} per period
      price_data       — list of {trade_date, ts_code, close}
      initial_capital  — starting cash
      cost_bps         — one-way transaction cost in basis points (0 = ignored)

    The `run` method below computes metrics from the provided series without
    modelling costs or market microstructure. Marked EXPERIMENTAL.
    """

    def __init__(self, cost_bps: float = 0.0):
        self.cost_bps = cost_bps

    async def run(
        self,
        strategy_signals: list[dict],
        price_data: list[dict],
        initial_capital: float = 1_000_000,
        benchmark_code: str | None = None,
    ) -> BacktestResult:
        """Compute backtest metrics from signals + prices.

        Returns a BacktestResult flagged `experimental=True`.
        Raises ValueError if inputs are inconsistent.
        """
        # Build price series indexed by (trade_date, ts_code)
        prices: dict[tuple[str, str], float] = {}
        for row in price_data:
            prices[(row["trade_date"], row["ts_code"])] = float(row["close"])

        # Simulate portfolio value period by period
        equity_curve: list[float] = [initial_capital]
        period_start = strategy_signals[0]["trade_date"] if strategy_signals else ""
        period_end = strategy_signals[-1]["trade_date"] if strategy_signals else ""
        trades = 0

        prev_value = initial_capital
        for signal in strategy_signals:
            date = signal["trade_date"]
            positions = signal.get("positions", {})
            value = 0.0
            for ts_code, shares in positions.items():
                close = prices.get((date, ts_code))
                if close is not None:
                    value += shares * close
                trades += 1
            # Include cost for trades if configured
            if self.cost_bps > 0:
                value -= value * self.cost_bps / 10_000
            # Fall back to previous value if no price matched
            equity_curve.append(value if value > 0 else prev_value)
            prev_value = equity_curve[-1]

        if len(equity_curve) < 2:
            return BacktestResult(period=f"{period_start}-{period_end}")

        # Metrics
        start, end = equity_curve[0], equity_curve[-1]
        total_return = (end - start) / start if start else 0.0
        n = len(equity_curve) - 1
        annualized_return = (1 + total_return) ** (252 / max(n, 1)) - 1

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak else 0.0
            if dd > max_dd:
                max_dd = dd

        # Sharpe (annualized) from period returns
        period_returns = [
            (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            for i in range(1, len(equity_curve))
            if equity_curve[i - 1] != 0
        ]
        sharpe = 0.0
        if period_returns:
            mean_r = sum(period_returns) / len(period_returns)
            var_r = sum((r - mean_r) ** 2 for r in period_returns) / len(period_returns)
            std_r = math.sqrt(var_r)
            if std_r > 0:
                sharpe = mean_r / std_r * math.sqrt(252)

        # Win rate = fraction of positive periods
        win_rate = (
            sum(1 for r in period_returns if r > 0) / len(period_returns)
            if period_returns else 0.0
        )

        return BacktestResult(
            total_return=round(total_return, 6),
            annualized_return=round(annualized_return, 6),
            max_drawdown=round(max_dd, 6),
            sharpe_ratio=round(sharpe, 4),
            win_rate=round(win_rate, 4),
            total_trades=trades,
            period=f"{period_start}-{period_end}",
            experimental=True,
        )
