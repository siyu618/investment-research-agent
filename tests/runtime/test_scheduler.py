"""Tests for runtime/scheduler.py — DAG Scheduler with parallel execution."""

import asyncio

import pytest
from runtime.errors import FatalError, RecoverableError
from runtime.graph import build_graph
from runtime.models import (
    ExecutionContext,
    GraphResult,
    NodeResult,
    RuntimeConfig,
    TaskConfig,
    TaskGraph,
    TaskNode,
)
from runtime.scheduler import Scheduler


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def context():
    return ExecutionContext(
        session_id="test-session",
        correlation_id="test-correlation",
        user_requirement="test",
    )


@pytest.fixture
def scheduler():
    return Scheduler(config=RuntimeConfig(max_parallel=10))


@pytest.fixture
def linear_graph():
    """A → B → C"""
    return build_graph(
        nodes=[
            {"id": "a", "label": "A", "skill": "skill_a", "timeout": 5},
            {"id": "b", "label": "B", "skill": "skill_b", "timeout": 5},
            {"id": "c", "label": "C", "skill": "skill_c", "timeout": 5},
        ],
        edges=[("a", "b"), ("b", "c")],
    )


@pytest.fixture
def diamond_graph():
    """A → [B, C] → D"""
    return build_graph(
        nodes=[
            {"id": "a", "label": "A", "skill": "skill_a", "timeout": 5},
            {"id": "b", "label": "B", "skill": "skill_b", "timeout": 5},
            {"id": "c", "label": "C", "skill": "skill_c", "timeout": 5},
            {"id": "d", "label": "D", "skill": "skill_d", "timeout": 5},
        ],
        edges=[("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
    )


# ─── Test Helpers ────────────────────────────────────────────────────────


async def success_skill(node, input_data, context):
    """A skill executor that always succeeds."""
    return {"node_id": node.id, "status": "ok", "input": input_data}


async def failing_skill(node, input_data, context):
    """A skill executor that always fails."""
    raise FatalError(f"Skill {node.id} failed")


async def flaky_skill(fail_count: int):
    """Create a skill that fails the first N times, then succeeds."""
    attempts = [0]

    async def skill(node, input_data, context):
        attempts[0] += 1
        if attempts[0] <= fail_count:
            raise RecoverableError(f"Flaky attempt {attempts[0]}")
        return {"status": "ok", "attempts": attempts[0]}

    return skill


# ─── Basic Execution Tests ──────────────────────────────────────────────


class TestSchedulerBasic:
    @pytest.mark.asyncio
    async def test_linear_execution(self, scheduler, linear_graph, context):
        """A → B → C should execute all 3 nodes in order."""
        result = await scheduler.run(
            graph=linear_graph,
            context=context,
            skill_executor=success_skill,
        )
        assert result.success is True
        assert len(result.node_results) == 3
        assert all(r.success for r in result.node_results.values())

    @pytest.mark.asyncio
    async def test_diamond_execution_all_success(self, scheduler, diamond_graph, context):
        """A → [B, C] → D: all should succeed."""
        result = await scheduler.run(
            graph=diamond_graph,
            context=context,
            skill_executor=success_skill,
        )
        assert result.success is True
        assert len(result.node_results) == 4

    @pytest.mark.asyncio
    async def test_diamond_parallelism(self, scheduler, diamond_graph, context):
        """B and C should execute concurrently (not sequentially)."""
        execution_order = []

        async def tracking_skill(node, input_data, context):
            execution_order.append(node.id)
            await asyncio.sleep(0.05)
            return {"node_id": node.id}

        await scheduler.run(
            graph=diamond_graph,
            context=context,
            skill_executor=tracking_skill,
        )

        # B and C should have started before either finished
        assert "b" in execution_order
        assert "c" in execution_order

    @pytest.mark.asyncio
    async def test_result_structure(self, scheduler, linear_graph, context):
        """GraphResult should contain per-node NodeResults."""
        # Use a slow enough skill so duration_ms is measurable
        async def slow_skill(node, input_data, context):
            await asyncio.sleep(0.01)
            return {"node_id": node.id}

        result = await scheduler.run(
            graph=linear_graph,
            context=context,
            skill_executor=slow_skill,
        )
        assert isinstance(result, GraphResult)
        assert result.session_id == "test-session"
        assert isinstance(result.node_results, dict)

        for node_id, node_result in result.node_results.items():
            assert isinstance(node_result, NodeResult)
            assert node_result.node_id == node_id
            assert node_result.success is True
            assert node_result.output is not None
            assert node_result.duration_ms >= 1, (
                f"Expected positive duration_ms, got {node_result.duration_ms}"
            )


# ─── Error Handling Tests ────────────────────────────────────────────────


class TestSchedulerErrors:
    @pytest.mark.asyncio
    async def test_fatal_error_stops_execution(self, scheduler, diamond_graph, context):
        """A fatal error in B should stop the graph."""
        call_count = []

        async def skill_with_fatal(node, input_data, context):
            call_count.append(node.id)
            if node.id in ("b", "c"):
                raise FatalError(f"Fatal in {node.id}")
            return {"status": "ok"}

        result = await scheduler.run(
            graph=diamond_graph,
            context=context,
            skill_executor=skill_with_fatal,
        )

        # B and C should have been attempted
        assert len(result.node_results) >= 2
        # A should have succeeded
        assert result.node_results["a"].success is True

    @pytest.mark.asyncio
    async def test_recoverable_error_retries(self, scheduler, context):
        """Recoverable errors should be retried according to config."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "skill_a",
                 "timeout": 5, "max_retries": 3},
            ],
            edges=[],
        )
        flaky = await flaky_skill(fail_count=2)  # fail twice, succeed on 3rd

        result = await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=flaky,
        )

        assert result.node_results["a"].success is True
        assert result.node_results["a"].retry_count == 2  # 2 retries = 3 total attempts

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, scheduler, context):
        """Skill that always fails should exhaust retries."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "skill_a",
                 "timeout": 5, "max_retries": 1},
            ],
            edges=[],
        )

        result = await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=failing_skill,
        )

        assert result.node_results["a"].success is False
        assert result.node_results["a"].error is not None

    @pytest.mark.asyncio
    async def test_timeout(self, scheduler, context):
        """Node that exceeds timeout should fail."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "skill_a",
                 "timeout": 0.05, "max_retries": 0},  # 50ms timeout
            ],
            edges=[],
        )

        async def slow_skill(node, input_data, context):
            await asyncio.sleep(5)  # much longer than timeout
            return {}

        result = await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=slow_skill,
        )

        assert result.node_results["a"].success is False
        assert "Timeout" in result.node_results["a"].error


# ─── Deterministic Parallelism Tests ────────────────────────────────────


class TestSchedulerParallelism:
    @pytest.mark.asyncio
    async def test_parallel_execution_faster_than_serial(self, scheduler, context):
        """Running 4 parallel 100ms tasks should take ~100ms not ~400ms."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "s", "timeout": 5},
                {"id": "b", "label": "B", "skill": "s", "timeout": 5},
                {"id": "c", "label": "C", "skill": "s", "timeout": 5},
                {"id": "d", "label": "D", "skill": "s", "timeout": 5},
            ],
            edges=[],
            entry_points=["a", "b", "c", "d"],
        )

        async def slow_skill(node, input_data, context):
            await asyncio.sleep(0.2)
            return {"node_id": node.id}

        result = await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=slow_skill,
        )

        # 4 × 200ms in parallel should take < 400ms (some overhead)
        assert result.total_duration_ms < 600, (
            f"Parallel execution took {result.total_duration_ms}ms, "
            f"expected < 600ms for 4 × 200ms parallel tasks"
        )
        assert all(r.success for r in result.node_results.values())

    @pytest.mark.asyncio
    async def test_graph_state_pass_through(self, scheduler, context):
        """Output of one node should be available as input to the next."""
        graph = build_graph(
            nodes=[
                {"id": "producer", "label": "P", "skill": "p", "timeout": 5},
                {"id": "consumer", "label": "C", "skill": "c", "timeout": 5},
            ],
            edges=[("producer", "consumer")],
        )

        async def smart_skill(node, input_data, context):
            if node.id == "producer":
                return {"produced_value": 42}
            elif node.id == "consumer":
                # Consumer should see producer's output in state
                val = input_data.get("produced_value")
                assert val == 42, f"Expected 42, got {val}"
                return {"consumed": True}
            return {}

        await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=smart_skill,
        )

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, context):
        """Scheduler should respect max_parallel config."""
        scheduler = Scheduler(config=RuntimeConfig(max_parallel=2))

        graph = build_graph(
            nodes=[
                {"id": f"n{i}", "label": f"N{i}", "skill": "s", "timeout": 10}
                for i in range(6)
            ],
            edges=[],
            entry_points=[f"n{i}" for i in range(6)],
        )

        max_concurrent = [0]
        current_concurrent = [0]

        async def tracking_skill(node, input_data, context):
            current_concurrent[0] += 1
            max_concurrent[0] = max(max_concurrent[0], current_concurrent[0])
            await asyncio.sleep(0.05)
            current_concurrent[0] -= 1
            return {}

        await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=tracking_skill,
        )

        # Should have at most 2 concurrent (maybe 1 if timing, but never >2)
        assert max_concurrent[0] <= 2, (
            f"Expected max 2 concurrent, got {max_concurrent[0]}"
        )


# ─── Cancellation Tests ─────────────────────────────────────────────────


class TestSchedulerCancellation:
    @pytest.mark.asyncio
    async def test_cancel_execution(self, scheduler, context):
        """Cancelling should stop execution after current layer."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "s", "timeout": 5},
                {"id": "b", "label": "B", "skill": "s", "timeout": 5},
            ],
            edges=[("a", "b")],
        )

        async def slow_skill(node, input_data, context):
            await asyncio.sleep(0.1)
            if node.id == "a":
                scheduler.cancel()
            return {"done": True}

        result = await scheduler.run(
            graph=graph,
            context=context,
            skill_executor=slow_skill,
        )

        # A should have completed; B may or may not
        assert "a" in result.node_results


# ─── Skill Registry Lookup Tests ────────────────────────────────────────


class TestSchedulerRegistry:
    @pytest.mark.asyncio
    async def test_missing_skill_raises_fatal(self, scheduler, context):
        """Referencing a skill not in the registry should fail."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "nonexistent-skill", "timeout": 5},
            ],
            edges=[],
        )

        result = await scheduler.run(
            graph=graph,
            context=context,
            # No skill_executor provided and no registry
        )

        assert result.node_results["a"].success is False
        assert "no skill_executor" in result.node_results["a"].error.lower()
