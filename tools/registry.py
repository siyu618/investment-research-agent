# Tool Registry — Metadata-rich tool management
#
# Every tool has: name, description, schema, capability, timeout, cost,
# version, permission, cache policy, rate limit.
#
# The Planner uses this registry for automatic tool discovery.
# The Runtime uses it for enforcement (timeout, rate limit, cache).
#
# Usage:
#     registry = ToolRegistry(event_bus=bus, cache=cache)
#     registry.register(get_stock_basic, ToolMetadata(
#         name="get_stock_basic",
#         description="List stocks by market/industry",
#         capability="market-data",
#         timeout=10, cost=1,
#     ))
#     result = await registry.invoke("get_stock_basic", {"market": "SSE"})

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from runtime.errors import FatalError, ToolError
from runtime.models import Event, EventType

# ─── Cache Policy ────────────────────────────────────────────────────────


@dataclass
class CachePolicy:
    """Cache policy for a tool's results.

    - ttl=0: no caching
    - ttl>0: cache for N seconds
    - key_prefix: prefix for cache keys (default: tool name)
    """
    ttl: int = 0
    key_prefix: str = ""
    enabled: bool = True


# ─── Tool Metadata ───────────────────────────────────────────────────────


class ToolCapability(str, Enum):
    """High-level capability categories for tool discovery."""
    MARKET_DATA = "market-data"
    FINANCIALS = "financials"
    MARKET_BEHAVIOR = "market-behavior"
    ANALYSIS = "analysis"
    DATA_STORAGE = "data-storage"
    BACKTEST = "backtest"
    UTILITY = "utility"


class ToolPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass
class ToolMetadata:
    """Rich metadata for a single tool.

    All fields except `name` and `description` have sensible defaults.
    The Planner reads these fields to understand what tools are available.
    """
    name: str
    description: str

    # JSON Schema for input parameters
    schema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
    })

    # JSON Schema for return value
    returns: dict = field(default_factory=lambda: {
        "type": "array",
    })

    # Capability category — used for discovery by the Planner
    capability: str = ToolCapability.UTILITY.value

    # Execution constraints
    timeout: int = 30                # Max execution time (seconds)
    cost: int = 1                    # Relative cost (1-10, for planner optimization)

    # Versioning
    version: str = "1.0.0"

    # Access control
    permission: str = ToolPermission.READ.value

    # Caching
    cache_policy: CachePolicy | None = None

    # Rate limiting — "N/interval" e.g. "200/min", "1000/hour"
    rate_limit: str | None = None

    # Known error types (for LLM reasoning about tool errors)
    errors: list[str] = field(default_factory=list)

    # Tags for filtering
    tags: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Result from invoking a tool."""
    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: int = 0
    cached: bool = False
    tool_name: str = ""


# ─── Rate Limiter ────────────────────────────────────────────────────────


class RateLimiter:
    """Simple token-bucket rate limiter per tool.

    In a production deployment, replace with Redis-based rate limiter.
    """

    def __init__(self, rate_limit: str):
        self.max_calls, self.interval = self._parse(rate_limit)
        self._timestamps: list[float] = []

    @staticmethod
    def _parse(rate_limit: str) -> tuple[int, float]:
        """Parse '200/min' → (200, 60.0), '1000/hour' → (1000, 3600.0)."""
        parts = rate_limit.split("/")
        count = int(parts[0])
        unit = parts[1]
        if unit in ("s", "sec", "second"):
            interval = 1.0
        elif unit in ("m", "min", "minute"):
            interval = 60.0
        elif unit in ("h", "hour"):
            interval = 3600.0
        else:
            interval = 60.0
        return count, interval

    def acquire(self) -> bool:
        """Try to acquire a permit. Returns True if allowed."""
        now = time.monotonic()
        cutoff = now - self.interval
        # Prune old entries
        self._timestamps = [t for t in self._timestamps if t > cutoff]

        if len(self._timestamps) >= self.max_calls:
            return False

        self._timestamps.append(now)
        return True


# ─── Tool Registry ───────────────────────────────────────────────────────


class ToolRegistry:
    """Central registry of all available tools.

    The registry owns:
    - Tool registration with rich metadata
    - Tool discovery by capability
    - Tool invocation with timeout, rate limiting, caching
    - Event emission for every invocation
    - Retry for recoverable errors
    """

    def __init__(
        self,
        event_bus: Any = None,
        cache: Any = None,
    ):
        self.event_bus = event_bus
        self.cache = cache  # runtime.cache.CacheProvider
        self._tools: dict[str, Callable] = {}
        self._metadata: dict[str, ToolMetadata] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}

    # ─── Registration ────────────────────────────────────────────────────

    def register(
        self,
        fn: Callable,
        metadata: ToolMetadata,
    ) -> None:
        """Register a tool function with its metadata.

        Args:
            fn: The callable implementing this tool.
                Can be sync or async; the registry handles both.
            metadata: Rich metadata for discovery and enforcement.
        """
        self._tools[metadata.name] = fn
        self._metadata[metadata.name] = metadata

        # Set up rate limiter if specified
        if metadata.rate_limit:
            self._rate_limiters[metadata.name] = RateLimiter(metadata.rate_limit)

    def register_from_yaml(self, tool_dir: str) -> int:
        """Register all tools defined in YAML files from a directory.

        Each YAML file should contain a mapping of tool names to
        ToolMetadata-compatible dicts. The implementation functions
        are loaded from the 'module' field in the YAML.

        Returns the number of tools registered.
        """
        from pathlib import Path

        import yaml

        count = 0
        for yaml_path in sorted(Path(tool_dir).glob("*.yaml")):
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            tools_data = data.get("tools", {})
            for name, meta_dict in tools_data.items():
                # Build ToolMetadata from dict
                meta = ToolMetadata(
                    name=name,
                    description=meta_dict.get("description", ""),
                    schema=meta_dict.get("schema", {}),
                    returns=meta_dict.get("returns", {}),
                    capability=meta_dict.get("capability", "utility"),
                    timeout=meta_dict.get("timeout", 30),
                    cost=meta_dict.get("cost", 1),
                    version=meta_dict.get("version", "1.0.0"),
                    permission=meta_dict.get("permission", "read"),
                    rate_limit=meta_dict.get("rate_limit"),
                    tags=meta_dict.get("tags", []),
                )

                # Set cache policy
                cache_cfg = meta_dict.get("cache_policy")
                if cache_cfg:
                    meta.cache_policy = CachePolicy(
                        ttl=cache_cfg.get("ttl", 0),
                        key_prefix=cache_cfg.get("key_prefix", name),
                        enabled=cache_cfg.get("enabled", True),
                    )

                # Load implementation from module
                module_path = meta_dict.get("module", "")
                fn: Callable | None = None
                if module_path:
                    fn = self._load_tool_impl(module_path)
                else:
                    fn = self._tools.get(name)
                    if fn is None:
                        continue

                self._tools[name] = fn
                self._metadata[name] = meta
                count += 1

        return count

    # ─── Discovery ───────────────────────────────────────────────────────

    def list_tools(self) -> list[ToolMetadata]:
        """List all registered tools with metadata."""
        return list(self._metadata.values())

    def get_tool(self, name: str) -> ToolMetadata | None:
        """Get tool metadata by name."""
        return self._metadata.get(name)

    def find_by_capability(self, capability: str) -> list[ToolMetadata]:
        """Find tools by capability category.

        Used by the Planner to discover which tools are needed
        for a given analysis task.
        """
        return [
            meta for meta in self._metadata.values()
            if meta.capability == capability
        ]

    def find_by_names(self, names: list[str]) -> list[ToolMetadata]:
        """Find tools by name. Unknown names are silently skipped."""
        return [
            meta for name, meta in self._metadata.items()
            if name in names
        ]

    def get_schemas_for_llm(self) -> list[dict]:
        """Return tool schemas formatted for LLM tool-use API.

        Compatible with OpenAI/Anthropic tool-use format.
        Each entry has: name, description, input_schema (JSON Schema).
        """
        schemas = []
        for meta in self._metadata.values():
            schema = {
                "name": meta.name,
                "description": meta.description,
                "input_schema": meta.schema,
            }
            schemas.append(schema)
        return schemas

    # ─── Invocation ──────────────────────────────────────────────────────

    async def invoke(
        self,
        tool_name: str,
        args: dict,
        correlation_id: str = "",
    ) -> ToolResult:
        """Invoke a tool with runtime-managed enforcement.

    The runtime enforces:
        - Tool existence check
        - Rate limiting
        - Cache lookup (if cache_policy configured)
        - Timeout
        - Event emission (ToolInvoked, ToolFinished, ToolFailed)
        - Error wrapping

        Args:
            tool_name: Name of the registered tool.
            args: Input arguments (validated by the tool's own schema).
            correlation_id: For event correlation.

        Returns:
            ToolResult with data or error.
        """
        start = time.monotonic()

        # 1. Check tool exists
        fn = self._tools.get(tool_name)
        meta = self._metadata.get(tool_name)
        if fn is None or meta is None:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found",
                tool_name=tool_name,
            )

        # 2. Rate limit check
        limiter = self._rate_limiters.get(tool_name)
        if limiter and not limiter.acquire():
            return ToolResult(
                success=False,
                error=f"Rate limit exceeded for '{tool_name}'",
                tool_name=tool_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # 3. Cache lookup
        cache_key = self._build_cache_key(tool_name, args)
        if meta.cache_policy and meta.cache_policy.enabled and meta.cache_policy.ttl > 0:
            if self.cache is not None:
                cached = await self.cache.get(cache_key)
                if cached is not None:
                    self._emit(EventType.TOOL_CACHE_HIT, {
                        "tool_name": tool_name,
                        "args_key": cache_key[:32],
                    })
                    return ToolResult(
                        success=True,
                        data=cached,
                        cached=True,
                        tool_name=tool_name,
                    )
                self._emit(EventType.TOOL_CACHE_MISS, {
                    "tool_name": tool_name,
                    "args_key": cache_key[:32],
                })

        # 4. Emit ToolInvoked
        self._emit(EventType.TOOL_INVOKED, {
            "tool_name": tool_name,
            "input": args,
        })

        # 5. Execute with timeout
        try:
            if inspect.iscoroutinefunction(fn):
                result = await asyncio.wait_for(
                    fn(**args),
                    timeout=meta.timeout,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(fn, **args),
                    timeout=meta.timeout,
                )
        except TimeoutError:
            duration = int((time.monotonic() - start) * 1000)
            self._emit(EventType.TOOL_FAILED, {
                "tool_name": tool_name,
                "error": f"Timeout after {meta.timeout}s",
                "recoverable": True,
            })
            raise ToolError(
                message=f"Tool '{tool_name}' timed out after {meta.timeout}s",
                tool_name=tool_name,
                recoverable=True,
            ) from None
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            self._emit(EventType.TOOL_FAILED, {
                "tool_name": tool_name,
                "error": str(e),
                "recoverable": False,
            })
            raise ToolError(
                message=f"Tool '{tool_name}' failed: {e}",
                tool_name=tool_name,
                recoverable=False,
            ) from e

        # 6. Cache result
        duration = int((time.monotonic() - start) * 1000)
        if meta.cache_policy and meta.cache_policy.enabled and meta.cache_policy.ttl > 0:
            if self.cache is not None:
                await self.cache.set(cache_key, result, meta.cache_policy.ttl)

        # 7. Emit ToolFinished
        self._emit(EventType.TOOL_FINISHED, {
            "tool_name": tool_name,
            "duration_ms": duration,
        })

        return ToolResult(
            success=True,
            data=result,
            duration_ms=duration,
            tool_name=tool_name,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_cache_key(tool_name: str, args: dict) -> str:
        """Build deterministic cache key from tool name and args."""
        canonical = json.dumps(args, sort_keys=True)
        arg_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return f"tool:{tool_name}:{arg_hash}"

    def _emit(self, event_type: str, payload: dict) -> None:
        """Emit event if event_bus is configured."""
        if self.event_bus is None:
            return
        event = Event(
            id=f"tool-{uuid.uuid4().hex[:8]}",
            type=event_type,
            timestamp=datetime.now().isoformat(),
            correlation_id="",
            payload=payload,
        )
        self.event_bus.emit(event)

    @staticmethod
    def _load_tool_impl(module_path: str) -> Callable:
        """Load a tool implementation from a module path.

        Supports:
          - "tools.tushare_mcp.server.get_stock_basic" → function
          - "tools.tushare_mcp.server.TushareTools.get_stock_basic" → method
        """
        import importlib
        parts = module_path.split(".")
        for i in range(len(parts), 0, -1):
            try:
                module_name = ".".join(parts[:i])
                module = importlib.import_module(module_name)
                # Try to traverse the remaining parts as attributes
                obj = module
                for attr in parts[i:]:
                    obj = getattr(obj, attr)
                if callable(obj):
                    return obj
            except (ImportError, AttributeError):
                continue
        raise FatalError(f"Cannot load tool implementation from '{module_path}'")
