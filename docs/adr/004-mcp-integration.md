# Architecture Decision Record: MCP Integration Strategy

**Status:** Accepted
**Decision:** #004
**Date:** 2026-07-28

## Context

The investment research agent needs access to Tushare financial data (stock prices, financial statements, market indicators). The agent's Executor invokes tools during analysis — these tools must be:

1. **Discoverable**: The agent needs to know what tools exist and how to call them.
2. **Validated**: Tool arguments must be validated before execution.
3. **Observable**: Every tool call should be logged for audit and debugging.
4. **Resilient**: API failures, rate limits, and transient errors must be handled gracefully.
5. **Testable**: Tools must be mockable for evaluation runs without real API access.

The Model Context Protocol (MCP) is the established standard for LLM tool invocation in the engineering-ai-standards framework.

## Decision

**Decision:** We will implement a **Tushare MCP Server** that wraps Tushare API calls as MCP tools, and a **Local Market Data Cache** layer that sits between the MCP server and the Tushare API.

The architecture is:

```
Agent Executor → MCP Client → Tushare MCP Server → Cache Layer → Tushare API
```

The MCP server exposes tools via the standard MCP protocol (JSON-RPC over stdio or HTTP). The Cache Layer uses SQLite to cache frequently accessed data (stock basics, trade calendar) and reduce Tushare API calls.

## Rationale

- **MCP = standard protocol**: The agent can discover tools, their schemas, and invoke them through a standardized interface. No custom tool-calling logic needed.
- **Cache Layer**: Tushare has API rate limits (200 queries/min for basic tokens). Caching prevents redundant calls — stock basics don't change intraday, and daily price data only needs one fetch per session.
- **Separation of concerns**: The MCP server handles protocol concerns (tool discovery, invocation, error wrapping). The agent focuses on analysis.
- **Testability**: The cache layer can be seeded with test data. Evaluation runs use cached data, not live API calls.
- **Idempotency**: All Tushare data tools are read-only. The MCP server enforces this — no write tools are exposed.

## Consequences

### Positive

- Standard tool interface means the Executor's tool-calling logic is generic, not Tushare-specific.
- Cache reduces API costs and improves analysis speed (data is served from local SQLite).
- MCP server can be developed and tested independently from the agent.
- Tool schemas are self-documenting — the agent reads the schema at discovery time.
- Switching data sources (e.g., from Tushare to a different provider) requires only changing the MCP server, not the agent.

### Negative

- MCP adds a process boundary (stdio/HTTP) — slightly higher latency than direct API calls (~1-5ms overhead, negligible).
- The MCP server needs its own configuration management (Tushare API token, cache settings).
- Cache invalidation logic needed (daily price data becomes stale after market close).

### Neutral

- The MCP server is a separate process. It can be started/stopped independently of the agent.
- The Cache Layer adds about 50 lines of code but eliminates ~80% of redundant API calls.

## Alternatives Considered

### Alternative 1: Direct Tushare API calls from agent

- **Description**: The Executor calls the Tushare Python SDK directly.
- **Pros**: Simplest implementation; no additional server process; lowest latency.
- **Cons**: No tool discovery; no schema validation; agent hard-coded to Tushare API; cannot mock without modifying agent code; violates MCP standard.
- **Why rejected**: Direct API coupling makes the agent untestable and non-portable. Violates the engineering-ai-standards tool-use pattern.

### Alternative 2: REST API wrapper (non-MCP)

- **Description**: A REST API server wrapping Tushare, called by the agent via HTTP.
- **Pros**: Language-agnostic; well-understood protocol; easy to test with curl.
- **Cons**: No standardized tool discovery (agent needs hardcoded endpoint list); no JSON Schema enforcement at protocol level; no standard error format.
- **Why rejected**: REST is more general but MCP is specifically designed for LLM tool invocation, with built-in discovery, schema validation, and structured errors.

### Alternative 3: MCP server without cache

- **Description**: MCP server that calls Tushare API directly on every request, no caching.
- **Pros**: Simpler MCP server; always fresh data.
- **Cons**: Wastes API quota on repeated calls within the same analysis session; slower response times for repeated queries.
- **Why rejected**: The cache layer is minimal code (SQLite upsert) and eliminates the majority of API calls within a session.

## Related Decisions

- [ADR-001: Agent Architecture](001-agent-architecture.md) (Executor uses MCP tools)
- [ADR-002: Skill System Design](002-skill-system.md) (Skills call MCP tools through Executor)
- engineering-ai-standards: `patterns/ai-agent/tool-use.md`, `skills/mcp-development/SKILL.md`

## Notes

Tushare API token must be configured via environment variable (`TUSHARE_TOKEN`). The MCP server validates token presence on startup and returns a clear error if missing.

Cache TTLs:
- Stock basics: 24 hours (refreshed daily)
- Trade calendar: 1 week (static within a year)
- Daily prices: 4 hours (refreshed after market close)
- Financial statements: Never (historical data is immutable)

The Backtest Engine MCP server (separate from Tushare MCP) is defined in Phase 4 and uses cached historical data rather than live API calls.
