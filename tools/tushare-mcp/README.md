# Tushare MCP Server

## Overview

Model Context Protocol (MCP) server that wraps Tushare financial data API endpoints as standardized MCP tools. Enables AI agents to discover and invoke Tushare data functions through the MCP protocol.

## Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_stock_basic` | List stocks by market/industry | market?, industry? |
| `get_daily_price` | Daily OHLCV for a stock | ts_code, start_date, end_date |
| `get_trade_calendar` | Trading calendar | start_date, end_date |
| `get_income_statement` | Income statement | ts_code, start_date, end_date |
| `get_balance_sheet` | Balance sheet | ts_code, start_date, end_date |
| `get_cashflow` | Cash flow statement | ts_code, start_date, end_date |
| `get_money_flow` | Money flow | ts_code, trade_date |
| `get_holder_change` | Holder changes | ts_code, start_date, end_date |
| `get_market_index` | Market index data | index_code, start_date, end_date |

## Configuration

Requires `TUSHARE_TOKEN` environment variable.

## Cache

Local SQLite cache at `~/.tushare_cache/`. TTL varies by data type:
- Stock basics: 24h
- Daily prices: 4h
- Financial statements: never (immutable)
