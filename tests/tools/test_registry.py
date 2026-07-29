"""Tests for tools/registry.py — Metadata-rich ToolRegistry."""

import asyncio

import pytest
from runtime.cache import TTLCache
from runtime.errors import ToolError
from tools.registry import (
    CachePolicy,
    RateLimiter,
    ToolMetadata,
    ToolRegistry,
    ToolResult,
)


# ─── Fixtures ────────────────────────────────────────────────────────────


def sample_tool_sync(market: str = "SSE", industry: str = None):
    """A synchronous test tool."""
    result = [{"ts_code": f"000001.{market}", "name": "Test Stock"}]
    if industry:
        result[0]["industry"] = industry
    return result


async def sample_tool_async(ts_code: str, start_date: str = "20240101"):
    """An asynchronous test tool."""
    await asyncio.sleep(0.01)
    return [
        {"ts_code": ts_code, "trade_date": "2024-01-02", "close": 10.5},
    ]


@pytest.fixture
def registry():
    return ToolRegistry()


@pytest.fixture
def cache():
    return TTLCache()


@pytest.fixture
def populated_registry(registry):
    registry.register(
        sample_tool_sync,
        ToolMetadata(
            name="get_stock_basic",
            description="List stocks by market/industry",
            capability="market-data",
            timeout=10,
            cost=1,
            schema={
                "type": "object",
                "properties": {
                    "market": {"type": "string", "enum": ["SSE", "SZSE"]},
                    "industry": {"type": "string"},
                },
            },
            cache_policy=CachePolicy(ttl=3600, key_prefix="stock_basic"),
        ),
    )
    registry.register(
        sample_tool_async,
        ToolMetadata(
            name="get_daily_price",
            description="Get daily price data",
            capability="market-data",
            timeout=15,
            cost=2,
            schema={
                "type": "object",
                "properties": {
                    "ts_code": {"type": "string"},
                    "start_date": {"type": "string"},
                },
            },
        ),
    )
    return registry


@pytest.fixture
def cached_registry(cache):
    reg = ToolRegistry(cache=cache)
    reg.register(
        sample_tool_sync,
        ToolMetadata(
            name="get_stock_basic",
            description="List stocks",
            capability="market-data",
            timeout=10,
            cache_policy=CachePolicy(ttl=3600, key_prefix="stock_basic"),
        ),
    )
    return reg


# ─── Registration Tests ─────────────────────────────────────────────────


class TestRegistration:
    def test_register_single(self, registry):
        registry.register(
            sample_tool_sync,
            ToolMetadata(name="test-tool", description="A test tool"),
        )
        assert len(registry.list_tools()) == 1

    def test_register_multiple(self, populated_registry):
        assert len(populated_registry.list_tools()) == 2

    def test_get_tool_metadata(self, populated_registry):
        meta = populated_registry.get_tool("get_stock_basic")
        assert meta is not None
        assert meta.name == "get_stock_basic"
        assert meta.capability == "market-data"
        assert meta.timeout == 10
        assert meta.cost == 1

    def test_get_tool_nonexistent(self, populated_registry):
        assert populated_registry.get_tool("nonexistent") is None

    def test_list_tools_returns_metadata(self, populated_registry):
        tools = populated_registry.list_tools()
        assert all(isinstance(t, ToolMetadata) for t in tools)


# ─── Discovery Tests ────────────────────────────────────────────────────


class TestDiscovery:
    def test_find_by_capability(self, populated_registry):
        tools = populated_registry.find_by_capability("market-data")
        assert len(tools) == 2  # both tools are market-data

    def test_find_by_capability_none(self, populated_registry):
        tools = populated_registry.find_by_capability("backtest")
        assert tools == []

    def test_find_by_names(self, populated_registry):
        tools = populated_registry.find_by_names(["get_stock_basic", "nonexistent"])
        assert len(tools) == 1
        assert tools[0].name == "get_stock_basic"

    def test_get_schemas_for_llm(self, populated_registry):
        schemas = populated_registry.get_schemas_for_llm()
        assert len(schemas) == 2
        for s in schemas:
            assert "name" in s
            assert "description" in s
            assert "input_schema" in s


# ─── Invocation Tests ───────────────────────────────────────────────────


class TestInvocation:
    @pytest.mark.asyncio
    async def test_invoke_sync_tool(self, populated_registry):
        result = await populated_registry.invoke(
            "get_stock_basic", {"market": "SSE"},
        )
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data is not None
        assert result.data[0]["ts_code"] == "000001.SSE"

    @pytest.mark.asyncio
    async def test_invoke_async_tool(self, populated_registry):
        result = await populated_registry.invoke(
            "get_daily_price", {"ts_code": "000001.SZ"},
        )
        assert result.success is True
        assert len(result.data) == 1
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_invoke_nonexistent(self, populated_registry):
        result = await populated_registry.invoke("nonexistent", {})
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_invoke_with_cache(self, cached_registry):
        # First call — miss, then store
        result1 = await cached_registry.invoke(
            "get_stock_basic", {"market": "SSE"},
        )
        assert result1.success is True
        assert result1.cached is False

        # Second call with same args — should be cache hit
        result2 = await cached_registry.invoke(
            "get_stock_basic", {"market": "SSE"},
        )
        assert result2.success is True
        assert result2.cached is True

    @pytest.mark.asyncio
    async def test_invoke_different_args_no_cache_hit(self, cached_registry):
        """Different args should produce a cache miss."""
        result1 = await cached_registry.invoke(
            "get_stock_basic", {"market": "SSE"},
        )
        assert result1.cached is False

        result2 = await cached_registry.invoke(
            "get_stock_basic", {"market": "SZSE"},
        )
        assert result2.cached is False


# ─── Rate Limiter Tests ─────────────────────────────────────────────────


class TestRateLimiter:
    def test_parse_minute(self):
        limiter = RateLimiter("200/min")
        assert limiter.max_calls == 200
        assert limiter.interval == 60.0

    def test_parse_hour(self):
        limiter = RateLimiter("1000/hour")
        assert limiter.max_calls == 1000
        assert limiter.interval == 3600.0

    def test_acquire_allows_within_limit(self):
        limiter = RateLimiter("3/min")
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is True

    def test_acquire_blocks_over_limit(self):
        limiter = RateLimiter("2/min")
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False  # third call blocked


# ─── ToolError Tests ────────────────────────────────────────────────────


class TestToolErrors:
    @pytest.mark.asyncio
    async def test_tool_error_class(self):
        err = ToolError(
            message="API rate limit exceeded",
            tool_name="get_stock_basic",
            recoverable=True,
        )
        assert err.tool_name == "get_stock_basic"
        assert err.recoverable is True

    @pytest.mark.asyncio
    async def test_tool_error_not_recoverable(self):
        err = ToolError(
            message="Invalid API token",
            tool_name="get_stock_basic",
            recoverable=False,
        )
        assert err.recoverable is False
