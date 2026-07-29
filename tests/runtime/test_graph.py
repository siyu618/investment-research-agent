"""Tests for runtime/graph.py — Task Graph validation and layering."""

import pytest
from runtime.graph import (
    ExecutionLayer,
    GraphState,
    GraphValidationError,
    build_graph,
    compute_layers,
    validate_graph,
)
from runtime.models import Edge, TaskGraph, TaskNode, TaskConfig


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def simple_linear_graph() -> TaskGraph:
    """A → B → C"""
    return TaskGraph(
        nodes={
            "a": TaskNode(id="a", label="Node A", skill="skill-a"),
            "b": TaskNode(id="b", label="Node B", skill="skill-b"),
            "c": TaskNode(id="c", label="Node C", skill="skill-c"),
        },
        edges=[
            Edge(source_id="a", target_id="b"),
            Edge(source_id="b", target_id="c"),
        ],
        entry_points=["a"],
        output_nodes=["c"],
    )


@pytest.fixture
def diamond_graph() -> TaskGraph:
    """    → B →
        A          D
          → C →       """
    return TaskGraph(
        nodes={
            "a": TaskNode(id="a", label="Start", skill="planner"),
            "b": TaskNode(id="b", label="Parallel B", skill="skill-b"),
            "c": TaskNode(id="c", label="Parallel C", skill="skill-c"),
            "d": TaskNode(id="d", label="Join D", skill="skill-d"),
        },
        edges=[
            Edge(source_id="a", target_id="b"),
            Edge(source_id="a", target_id="c"),
            Edge(source_id="b", target_id="d"),
            Edge(source_id="c", target_id="d"),
        ],
        entry_points=["a"],
        output_nodes=["d"],
    )


@pytest.fixture
def investment_research_graph() -> TaskGraph:
    """Research workflow: planner → data → [fund, tech, val, risk] → portfolio → verify → report"""
    return TaskGraph(
        nodes={
            "plan": TaskNode(id="plan", label="Planner", skill="planner"),
            "data": TaskNode(id="data", label="Data", skill="data-collector"),
            "fund": TaskNode(id="fund", label="Fundamental", skill="fundamental-analysis"),
            "tech": TaskNode(id="tech", label="Technical", skill="technical-analysis"),
            "val": TaskNode(id="val", label="Valuation", skill="valuation-analysis"),
            "risk": TaskNode(id="risk", label="Risk", skill="risk-analysis"),
            "port": TaskNode(id="port", label="Portfolio", skill="portfolio-selection"),
            "verify": TaskNode(id="verify", label="Verifier", skill="verifier"),
            "report": TaskNode(id="report", label="Report", skill="report-generator"),
        },
        edges=[
            Edge("plan", "data"),
            Edge("data", "fund"), Edge("data", "tech"),
            Edge("data", "val"), Edge("data", "risk"),
            Edge("fund", "port"), Edge("tech", "port"),
            Edge("val", "port"), Edge("risk", "port"),
            Edge("port", "verify"),
            Edge("verify", "report"),
        ],
        entry_points=["plan"],
        output_nodes=["report"],
    )


# ─── Graph Validation Tests ──────────────────────────────────────────────


class TestGraphValidation:
    def test_validates_simple_linear(self, simple_linear_graph):
        """A linear graph should pass validation."""
        validate_graph(simple_linear_graph)  # no error

    def test_validates_diamond(self, diamond_graph):
        """A diamond graph should pass validation."""
        validate_graph(diamond_graph)  # no error

    def test_validates_complex_research(self, investment_research_graph):
        """The complex research workflow should pass validation."""
        validate_graph(investment_research_graph)  # no error

    def test_detects_missing_node(self, simple_linear_graph):
        """An edge referencing a non-existent node should fail."""
        simple_linear_graph.edges.append(Edge(source_id="a", target_id="nonexistent"))
        with pytest.raises(GraphValidationError, match="not found"):
            validate_graph(simple_linear_graph)

    def test_detects_cycle(self):
        """A → B → C → A should fail."""
        graph = TaskGraph(
            nodes={
                "a": TaskNode(id="a", label="A", skill="s"),
                "b": TaskNode(id="b", label="B", skill="s"),
                "c": TaskNode(id="c", label="C", skill="s"),
            },
            edges=[
                Edge("a", "b"), Edge("b", "c"), Edge("c", "a"),
            ],
            entry_points=["a"],
        )
        with pytest.raises(GraphValidationError, match="Cycle detected"):
            validate_graph(graph)

    def test_detects_self_loop(self):
        """A → A should fail."""
        graph = TaskGraph(
            nodes={"a": TaskNode(id="a", label="A", skill="s")},
            edges=[Edge("a", "a")],
            entry_points=["a"],
        )
        with pytest.raises(GraphValidationError, match="Cycle detected"):
            validate_graph(graph)

    def test_entry_point_with_inbound_edge(self):
        """An entry point with inbound edges should fail."""
        graph = TaskGraph(
            nodes={
                "a": TaskNode(id="a", label="A", skill="s"),
                "b": TaskNode(id="b", label="B", skill="s"),
            },
            edges=[Edge("a", "b")],
            entry_points=["b"],  # b has inbound edge
        )
        with pytest.raises(GraphValidationError, match="inbound"):
            validate_graph(graph)

    def test_entry_point_not_found(self):
        """An entry point referencing a non-existent node should fail."""
        graph = TaskGraph(
            nodes={"a": TaskNode(id="a", label="A", skill="s")},
            edges=[],
            entry_points=["nonexistent"],
        )
        with pytest.raises(GraphValidationError, match="not a defined node"):
            validate_graph(graph)

    def test_unreachable_node(self):
        """A node not reachable from entry points should fail."""
        graph = TaskGraph(
            nodes={
                "a": TaskNode(id="a", label="A", skill="s"),
                "b": TaskNode(id="b", label="B", skill="s"),
            },
            edges=[],  # no edges → b unreachable
            entry_points=["a"],
        )
        with pytest.raises(GraphValidationError, match="not reachable"):
            validate_graph(graph)


# ─── Topological Sort / Layering Tests ───────────────────────────────────


class TestComputeLayers:
    def test_linear_layers(self, simple_linear_graph):
        """A → B → C should produce 3 layers: [A], [B], [C]"""
        layers = compute_layers(simple_linear_graph)
        assert len(layers) == 3
        assert layers[0].node_ids == ["a"]
        assert layers[1].node_ids == ["b"]
        assert layers[2].node_ids == ["c"]

    def test_diamond_parallel_layers(self, diamond_graph):
        """A → [B, C] → D should produce 3 layers"""
        layers = compute_layers(diamond_graph)
        assert len(layers) == 3
        assert layers[0].node_ids == ["a"]
        # Layer 1: B and C can run in parallel
        assert set(layers[1].node_ids) == {"b", "c"}
        assert layers[2].node_ids == ["d"]

    def test_investment_research_parallelism(self, investment_research_graph):
        """The research workflow should have 7 layers with layer 2 running 4 skills in parallel"""
        layers = compute_layers(investment_research_graph)
        assert len(layers) >= 5  # at minimum 5 layers

        # Find the parallel analysis layer (should contain fund, tech, val, risk)
        parallel_layer = None
        for layer in layers:
            if len(layer.node_ids) >= 4:
                parallel_layer = layer
                break

        assert parallel_layer is not None, "Expected a layer with 4+ parallel nodes"
        assert set(parallel_layer.node_ids) == {"fund", "tech", "val", "risk"}

    def test_single_node_graph(self):
        """A single node graph should produce 1 layer."""
        graph = TaskGraph(
            nodes={"a": TaskNode(id="a", label="A", skill="s")},
            edges=[],
            entry_points=["a"],
            output_nodes=["a"],
        )
        layers = compute_layers(graph)
        assert len(layers) == 1
        assert layers[0].node_ids == ["a"]

    def test_fan_in_fan_out(self):
        """[A, B] → C → [D, E] should have 3 layers"""
        nodes = {
            "a": TaskNode(id="a", label="A", skill="s"),
            "b": TaskNode(id="b", label="B", skill="s"),
            "c": TaskNode(id="c", label="C", skill="s"),
            "d": TaskNode(id="d", label="D", skill="s"),
            "e": TaskNode(id="e", label="E", skill="s"),
        }
        graph = TaskGraph(
            nodes=nodes,
            edges=[
                Edge("a", "c"), Edge("b", "c"),
                Edge("c", "d"), Edge("c", "e"),
            ],
            entry_points=["a", "b"],
            output_nodes=["d", "e"],
        )
        layers = compute_layers(graph)
        assert len(layers) == 3
        assert set(layers[0].node_ids) == {"a", "b"}
        assert layers[1].node_ids == ["c"]
        assert set(layers[2].node_ids) == {"d", "e"}

    def test_chained_diamond(self):
        """A → [B, C] → D → [E, F] → G: should have 5 layers"""
        nodes = {
            "a": TaskNode(id="a", label="A", skill="s"),
            "b": TaskNode(id="b", label="B", skill="s"),
            "c": TaskNode(id="c", label="C", skill="s"),
            "d": TaskNode(id="d", label="D", skill="s"),
            "e": TaskNode(id="e", label="E", skill="s"),
            "f": TaskNode(id="f", label="F", skill="s"),
            "g": TaskNode(id="g", label="G", skill="s"),
        }
        graph = TaskGraph(
            nodes=nodes,
            edges=[
                Edge("a", "b"), Edge("a", "c"),
                Edge("b", "d"), Edge("c", "d"),
                Edge("d", "e"), Edge("d", "f"),
                Edge("e", "g"), Edge("f", "g"),
            ],
            entry_points=["a"],
            output_nodes=["g"],
        )
        layers = compute_layers(graph)
        assert len(layers) == 5
        assert layers[0].node_ids == ["a"]                # A
        assert set(layers[1].node_ids) == {"b", "c"}        # B, C
        assert layers[2].node_ids == ["d"]                  # D
        assert set(layers[3].node_ids) == {"e", "f"}        # E, F
        assert layers[4].node_ids == ["g"]                  # G


# ─── GraphState Tests ───────────────────────────────────────────────────


class TestGraphState:
    def test_basic_read_write(self):
        state = GraphState({"initial": "value"})
        assert state.get("initial") == "value"
        state.set("key2", "value2")
        assert state.get("key2") == "value2"

    def test_default(self):
        state = GraphState()
        assert state.get("nonexistent", "default") == "default"
        assert state.get("nonexistent") is None

    def test_snapshot(self):
        state = GraphState({"a": 1, "b": 2})
        snap = state.snapshot()
        assert snap == {"a": 1, "b": 2}
        # Snapshot is a copy
        snap["a"] = 99
        assert state.get("a") == 1

    def test_update(self):
        state = GraphState({"a": 1})
        state.update({"b": 2, "c": 3})
        assert state.get("a") == 1
        assert state.get("b") == 2
        assert state.get("c") == 3

    def test_keys(self):
        state = GraphState({"a": 1, "b": 2})
        assert state.keys == {"a", "b"}


# ─── build_graph Tests ──────────────────────────────────────────────────


class TestBuildGraph:
    def test_basic_graph(self):
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "s1"},
                {"id": "b", "label": "B", "skill": "s2"},
            ],
            edges=[("a", "b")],
        )
        assert isinstance(graph, TaskGraph)
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert graph.entry_points == ["a"]
        assert graph.output_nodes == ["b"]

    def test_auto_entry_points(self):
        """Entry points should be nodes with no incoming edges."""
        graph = build_graph(
            nodes=[
                {"id": "a", "label": "A", "skill": "s1"},
                {"id": "b", "label": "B", "skill": "s2"},
                {"id": "c", "label": "C", "skill": "s3"},
            ],
            edges=[("a", "b"), ("b", "c")],
        )
        assert graph.entry_points == ["a"]
        assert graph.output_nodes == ["c"]

    def test_auto_with_branching(self):
        """With branching, nodes with no incoming or outgoing edges should be detected."""
        graph = build_graph(
            nodes=[
                {"id": "a", "skill": "s1"},
                {"id": "b", "skill": "s2"},
                {"id": "c", "skill": "s3"},
            ],
            edges=[("a", "b"), ("a", "c")],
        )
        assert graph.entry_points == ["a"]
        assert set(graph.output_nodes) == {"b", "c"}

    def test_custom_config(self):
        graph = build_graph(
            nodes=[
                {
                    "id": "a", "label": "A", "skill": "s1",
                    "timeout": 120, "max_retries": 5,
                    "tags": ["critical"],
                },
            ],
            edges=[],
        )
        node = graph.nodes["a"]
        assert node.config.timeout == 120
        assert node.config.max_retries == 5
        assert node.tags == ["critical"]

    def test_invalid_graph_raises(self):
        """Cyclic graphs should raise during build."""
        with pytest.raises(GraphValidationError):
            build_graph(
                nodes=[
                    {"id": "a", "skill": "s1"},
                    {"id": "b", "skill": "s2"},
                    {"id": "c", "skill": "s3"},
                ],
                edges=[("a", "b"), ("b", "c"), ("c", "a")],
            )
