# Runtime Framework — Workflow Loader
#
# Loads workflow definitions from YAML files and converts them
# to executable TaskGraphs.
#
# Usage:
#     registry = WorkflowRegistry("workflows/graphs")
#     workflow = registry.get("investment-research")
#     graph = workflow.graph  # Ready for Scheduler

from __future__ import annotations

from pathlib import Path

from runtime.graph import build_graph
from runtime.models import TaskGraph, WorkflowDefinition

# ─── Workflow YAML Format ──────────────────────────────────────────────

EXPECTED_YAML_FORMAT = """
name: workflow-name
version: "2.0.0"
description: Description of this workflow
config:
  max_retries: 2
  default_timeout: 60

nodes:
  - id: node-1
    label: "Human-Readable Label"
    skill: skill-name
    timeout: 30
    max_retries: 2
    tags: [tag1, tag2]

  - id: node-2
    label: "Another Node"
    skill: another-skill
    timeout: 60

edges:
  - from: node-1
    to: node-2

  - from: node-1
    to: node-3

entry_points: [node-1]
output_nodes: [node-3]
"""


# ─── Workflow Loader ────────────────────────────────────────────────────


class WorkflowLoadError(Exception):
    """Raised when a workflow definition cannot be loaded."""


def load_workflow_from_dict(data: dict) -> WorkflowDefinition:
    """Load a WorkflowDefinition from a parsed YAML dict.

    Args:
        data: Parsed YAML dict with the structure shown above.

    Returns:
        A validated WorkflowDefinition ready for execution.
    """
    name = data.get("name", "")
    if not name:
        raise WorkflowLoadError("Workflow 'name' is required")

    version = data.get("version", "1.0.0")
    description = data.get("description", "")
    config = data.get("config", {})

    # Parse nodes
    raw_nodes = data.get("nodes", [])
    if not raw_nodes:
        raise WorkflowLoadError(f"Workflow '{name}' has no nodes defined")

    # Parse edges
    raw_edges = data.get("edges", [])

    # Convert edges to tuple format
    edges: list[tuple[str, str]] = []
    for e in raw_edges:
        source = e.get("from", "")
        target = e.get("to", "")
        if isinstance(target, list):
            for t in target:
                edges.append((source, t))
        else:
            edges.append((source, target))

    # Apply global config to nodes that don't specify their own
    for node in raw_nodes:
        if "timeout" not in node and "default_timeout" in config:
            node["timeout"] = config["default_timeout"]
        if "max_retries" not in node and "max_retries" in config:
            node["max_retries"] = config["max_retries"]

    entry_points = data.get("entry_points")
    output_nodes = data.get("output_nodes")

    # Build and validate the TaskGraph
    graph = build_graph(
        nodes=raw_nodes,
        edges=edges,
        entry_points=entry_points,
        output_nodes=output_nodes,
    )

    return WorkflowDefinition(
        name=name,
        version=version,
        description=description,
        graph=graph,
        input_schema=data.get("input_schema", {}),
        output_schema=data.get("output_schema", {}),
        tags=data.get("tags", []),
    )


def load_workflow_from_yaml(filepath: str) -> WorkflowDefinition:
    """Load a WorkflowDefinition from a YAML file.

    Args:
        filepath: Path to a .yaml workflow definition file.

    Returns:
        A validated WorkflowDefinition.
    """
    import yaml

    path = Path(filepath)
    if not path.exists():
        raise WorkflowLoadError(f"Workflow file not found: {filepath}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if data is None:
        raise WorkflowLoadError(f"Empty workflow file: {filepath}")

    return load_workflow_from_dict(data)


# ─── Workflow Registry ─────────────────────────────────────────────────


class WorkflowRegistry:
    """Registry of workflow definitions loaded from YAML files.

    Usage:
        registry = WorkflowRegistry("workflows/graphs")
        workflow = registry.get("investment-research")
        graph = workflow.graph
    """

    def __init__(self, directory: str):
        self.directory = Path(directory)
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all .yaml workflow files from the directory."""
        if not self.directory.exists():
            return

        for filepath in sorted(self.directory.glob("*.yaml")):
            try:
                wf = load_workflow_from_yaml(str(filepath))
                self._workflows[wf.name] = wf
            except Exception as e:
                import warnings
                warnings.warn(
                    f"Failed to load workflow '{filepath.name}': {e}",
                    stacklevel=2,
                )

    def get(self, name: str) -> WorkflowDefinition | None:
        """Get a workflow by name."""
        return self._workflows.get(name)

    def list(self) -> list[WorkflowDefinition]:
        """List all loaded workflows."""
        return list(self._workflows.values())

    def reload(self) -> None:
        """Reload all workflows from disk."""
        self._workflows.clear()
        self._load_all()

    @property
    def count(self) -> int:
        return len(self._workflows)

    def get_graph(self, name: str) -> TaskGraph | None:
        """Get the TaskGraph for a workflow by name."""
        wf = self.get(name)
        return wf.graph if wf else None
