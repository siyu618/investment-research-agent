# Runtime Framework — Task Graph Engine
#
# Graph validation, topological sort, and layer computation.
# The TaskGraph is a DAG of executable nodes with dependency edges.
# The Scheduler uses these functions to orchestrate parallel execution.

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from runtime.models import (
    Edge,
    GraphResult,
    NodeResult,
    TaskConfig,
    TaskGraph,
    TaskNode,
)


# ─── Graph Validation ────────────────────────────────────────────────────


class GraphValidationError(Exception):
    """Raised when a TaskGraph fails validation."""


def validate_graph(graph: TaskGraph) -> None:
    """Validate a TaskGraph before execution.

    Checks:
    1. No duplicate node IDs
    2. All edge references resolve to existing nodes
    3. Entry points exist and have no inbound edges
    4. No cycles (DAG constraint)
    5. Output nodes exist and are reachable
    """
    node_ids = set(graph.nodes.keys())

    # 1. Entry points must be valid nodes
    for ep in graph.entry_points:
        if ep not in node_ids:
            raise GraphValidationError(
                f"Entry point '{ep}' is not a defined node. "
                f"Available nodes: {sorted(node_ids)}"
            )

    # 2. All edge references must resolve
    for edge in graph.edges:
        if edge.source_id not in node_ids:
            raise GraphValidationError(
                f"Edge source '{edge.source_id}' not found in nodes. "
                f"Available: {sorted(node_ids)}"
            )
        if edge.target_id not in node_ids:
            raise GraphValidationError(
                f"Edge target '{edge.target_id}' not found in nodes. "
                f"Available: {sorted(node_ids)}"
            )

    # 3. Output nodes must exist
    for on in graph.output_nodes:
        if on not in node_ids:
            raise GraphValidationError(
                f"Output node '{on}' is not a defined node"
            )

    # 4. Cycle detection via DFS (run before entry point checks
    #    so cyclic graphs are diagnosed as cycles, not as inbound edges)
    _detect_cycles(graph)

    # 5. Entry points must have no inbound edges
    inbound: dict[str, list[Edge]] = {nid: [] for nid in node_ids}
    for edge in graph.edges:
        inbound[edge.target_id].append(edge)

    for ep in graph.entry_points:
        if inbound[ep]:
            raise GraphValidationError(
                f"Entry point '{ep}' has inbound edges from: "
                f"{[e.source_id for e in inbound[ep]]}. "
                f"Entry points must have no dependencies."
            )

    # 6. All nodes reachable from entry points
    _check_reachability(graph)

    # 7. Entry point auto-detection if not explicitly set
    if not graph.entry_points:
        auto_entry_points = [
            nid for nid, edges in inbound.items() if not edges
        ]
        if auto_entry_points:
            # Not setting, just warning
            pass


def _detect_cycles(graph: TaskGraph) -> None:
    """Detect cycles using DFS (directed graph)."""
    VISITING, VISITED = 1, 2
    state: dict[str, int] = {}

    def dfs(node_id: str, path: list[str]) -> None:
        if node_id in state:
            if state[node_id] == VISITING:
                cycle_path = path[path.index(node_id):] + [node_id]
                raise GraphValidationError(
                    f"Cycle detected in graph: {' → '.join(cycle_path)}"
                )
            return

        state[node_id] = VISITING
        path.append(node_id)

        for edge in graph.edges:
            if edge.source_id == node_id:
                dfs(edge.target_id, path)

        path.pop()
        state[node_id] = VISITED

    for node_id in graph.nodes:
        if node_id not in state:
            dfs(node_id, [])


def _check_reachability(graph: TaskGraph) -> None:
    """Ensure all nodes are reachable from entry points."""
    reachable: set[str] = set(graph.entry_points)
    queue = deque(graph.entry_points)

    while queue:
        current = queue.popleft()
        for edge in graph.edges:
            if edge.source_id == current and edge.target_id not in reachable:
                reachable.add(edge.target_id)
                queue.append(edge.target_id)

    unreachable = set(graph.nodes.keys()) - reachable
    if unreachable:
        raise GraphValidationError(
            f"Nodes not reachable from entry points: {sorted(unreachable)}"
        )


# ─── Topological Sort / Layering ────────────────────────────────────────


@dataclass
class ExecutionLayer:
    """A layer of nodes that can execute in parallel.

    All nodes in a layer have their dependencies satisfied
    and can run concurrently.
    """
    index: int
    node_ids: list[str]


def compute_layers(graph: TaskGraph) -> list[ExecutionLayer]:
    """Compute execution layers via topological sort.

    Returns layers where each layer contains nodes that can
    execute in parallel (all dependencies are in earlier layers).

    Example:
        Layer 0: [planner]
        Layer 1: [data-collector]
        Layer 2: [fundamental, technical, valuation, risk]  ← parallel
        Layer 3: [portfolio]
        Layer 4: [verify]
        Layer 5: [report]
    """
    # Compute in-degree (number of unresolved dependencies)
    in_degree: dict[str, int] = {nid: 0 for nid in graph.nodes}
    adjacency: dict[str, list[str]] = {nid: [] for nid in graph.nodes}

    for edge in graph.edges:
        in_degree[edge.target_id] += 1
        adjacency[edge.source_id].append(edge.target_id)

    # Start with entry points (in_degree == 0)
    queue = deque(
        nid for nid, deg in in_degree.items() if deg == 0
    )
    if not queue:
        # Fallback: use explicitly declared entry points
        for ep in graph.entry_points:
            if ep in in_degree:
                in_degree[ep] = 0
                queue.append(ep)

    layers: list[ExecutionLayer] = []
    visited: set[str] = set()

    while queue:
        # All nodes currently in the queue have their deps satisfied
        current_layer_ids = list(queue)

        # Process this layer
        layers.append(ExecutionLayer(
            index=len(layers),
            node_ids=list(current_layer_ids),
        ))

        # Mark all as visited and advance their dependents
        for _ in range(len(current_layer_ids)):
            node_id = queue.popleft()
            visited.add(node_id)

            for successor in adjacency[node_id]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

    # Check all nodes were visited
    unvisited = set(graph.nodes.keys()) - visited
    if unvisited:
        raise GraphValidationError(
            f"Topological sort incomplete: {len(unvisited)} nodes "
            f"not placed: {sorted(unvisited)}"
        )

    return layers


# ─── Graph Execution State ──────────────────────────────────────────────


class GraphState:
    """Shared state that flows through graph execution.

    Each node reads from and writes to this state.
    The Scheduler manages state lifecycle.
    """

    def __init__(self, initial: Optional[dict] = None):
        self._data: dict[str, Any] = dict(initial or {})

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from shared state."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a value to shared state."""
        self._data[key] = value

    def update(self, mapping: dict) -> None:
        """Batch update shared state."""
        self._data.update(mapping)

    def snapshot(self) -> dict:
        """Return a copy of the entire state (for node input)."""
        return dict(self._data)

    @property
    def keys(self) -> set:
        return set(self._data.keys())


# ─── TaskNode Convenience Builder ───────────────────────────────────────


def build_graph(
    nodes: list[dict],
    edges: list[tuple[str, str]],
    entry_points: Optional[list[str]] = None,
    output_nodes: Optional[list[str]] = None,
) -> TaskGraph:
    """Convenience builder for creating TaskGraphs from dicts.

    Args:
        nodes: List of node dicts with keys:
            id, label, skill, [timeout], [max_retries], [tags]
        edges: List of (source_id, target_id) tuples
        entry_points: Node IDs with no dependencies (auto-detect if None)
        output_nodes: Node IDs that produce final output

    Returns:
        A validated TaskGraph ready for execution.
    """
    graph_nodes: dict[str, TaskNode] = {}
    for n in nodes:
        cfg = TaskConfig(
            timeout=n.get("timeout", 60),
            max_retries=n.get("max_retries", 2),
        )
        graph_nodes[n["id"]] = TaskNode(
            id=n["id"],
            label=n.get("label", n["id"]),
            skill=n["skill"],
            config=cfg,
            tags=n.get("tags", []),
        )

    graph_edges = [
        Edge(source_id=s, target_id=t) for s, t in edges
    ]

    # Auto-detect entry points
    if entry_points is None:
        all_targets = {t for _, t in edges}
        entry_points = [nid for nid in graph_nodes if nid not in all_targets]

    if output_nodes is None:
        all_sources = {s for s, _ in edges}
        output_nodes = [nid for nid in graph_nodes if nid not in all_sources]

    graph = TaskGraph(
        nodes=graph_nodes,
        edges=graph_edges,
        entry_points=entry_points,
        output_nodes=output_nodes,
    )

    validate_graph(graph)
    return graph
