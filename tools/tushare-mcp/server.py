# Tushare MCP Server — Expose Tushare API as MCP tools
# TODO: Implement MCP server using MCP Python SDK
# Reference: https://github.com/modelcontextprotocol/python-sdk

"""
MCP Server for Tushare financial data.

Usage:
    # Start stdio server (for agent integration)
    python -m tools.tushare_mcp.server

    # Test a tool
    python -m tools.tushare_mcp.server --test get_stock_basic '{"market": "SSE"}'
"""

import os
from typing import Optional

# Mock implementation — will use tushare SDK and MCP SDK in production


def get_stock_basic(
    market: Optional[str] = None,
    industry: Optional[str] = None,
) -> list[dict]:
    """List stocks with basic info filtered by market and/or industry.

    Args:
        market: Market code (SSE, SZSE, or None for all)
        industry: Industry classification

    Returns:
        List of stock basic info dicts
    """
    # TODO: Implement via tushare.pro_api().stock_basic()
    raise NotImplementedError(
        "Tushare MCP server not yet connected. "
        "Set TUSHARE_TOKEN and install tushare package."
    )


def get_daily_price(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get daily OHLCV price data.

    Args:
        ts_code: Stock code (e.g., '000001.SZ')
        start_date: Start date YYYYMMDD
        end_date: End date YYYYMMDD

    Returns:
        List of daily price dicts
    """
    # TODO: Implement via tushare.pro_api().daily()
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )


def get_income_statement(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get income statement data.

    Args:
        ts_code: Stock code
        start_date: Start date YYYYMMDD
        end_date: End date YYYYMMDD

    Returns:
        List of income statement dicts
    """
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )


def get_balance_sheet(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get balance sheet data."""
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )


def get_cashflow(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get cash flow statement data."""
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )


def get_trade_calendar(
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get trading calendar dates."""
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )


def get_money_flow(
    ts_code: str,
    trade_date: Optional[str] = None,
) -> list[dict]:
    """Get money flow data."""
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )


def get_market_index(
    index_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Get market index OHLCV data."""
    raise NotImplementedError(
        "Tushare MCP server not yet connected."
    )
