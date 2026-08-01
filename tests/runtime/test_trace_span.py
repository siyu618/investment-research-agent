"""Tests for trace_span — real duration, hashes, status."""

import asyncio

import pytest
from runtime.tracing.trace_span import SpanEntry, trace_span


class TestTraceSpan:
    @pytest.mark.asyncio
    async def test_ok_records_real_duration(self):
        sink: list[dict] = []
        async with trace_span("run1", "s1", "tool", "get_price", sink=sink) as span:
            span.set_input({"ts_code": "600519.SH"})
            await asyncio.sleep(0.01)
            span.set_output([{"close": 100.0}])
        assert len(sink) == 1
        rec = sink[0]
        assert rec["status"] == "ok"
        assert rec["duration_ms"] >= 10  # real elapsed time
        assert rec["input_hash"]
        assert rec["output_hash"]
        assert rec["input_summary"] != ""
        assert rec["output_size"] > 0

    @pytest.mark.asyncio
    async def test_error_records_status_and_message(self):
        sink: list[dict] = []
        with pytest.raises(RuntimeError, match="boom"):
            async with trace_span("run1", "s2", "skill", "fund", sink=sink) as span:
                span.set_input({"x": 1})
                await asyncio.sleep(0.005)
                raise RuntimeError("boom")
        assert len(sink) == 1
        rec = sink[0]
        assert rec["status"] == "error"
        assert "boom" in rec["error"]
        assert rec["duration_ms"] >= 5

    @pytest.mark.asyncio
    async def test_no_sink_does_not_crash(self):
        async with trace_span("run1", "s3", "llm", "parse") as span:
            span.set_input("requirement")
            span.set_output({"objective": "value"})
        # no sink → nothing appended, no error

    @pytest.mark.asyncio
    async def test_hash_is_stable_across_calls(self):
        sink: list[dict] = []
        async with trace_span("r", "s", "tool", "t", sink=sink) as sp:
            sp.set_output({"a": 1, "b": 2})
        h1 = sink[0]["output_hash"]
        sink.clear()
        async with trace_span("r", "s", "tool", "t", sink=sink) as sp:
            sp.set_output({"a": 1, "b": 2})
        assert sink[0]["output_hash"] == h1

    @pytest.mark.asyncio
    async def test_retry_count_passthrough(self):
        sink: list[dict] = []
        async with trace_span("r", "s", "skill", "sk", retry_count=2, sink=sink) as sp:
            sp.set_output({"score": 0.5})
        assert sink[0]["retry_count"] == 2

    def test_span_entry_manual(self):
        e = SpanEntry("r", "s", "tool", "t")
        e.set_input({"k": "v"})
        e.set_output({"result": 1})
        d = e.finalize()
        assert d["duration_ms"] >= 0
        assert d["input_hash"] and d["output_hash"]
        assert d["status"] == "ok"
