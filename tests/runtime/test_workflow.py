"""Tests for runtime/workflow.py — Workflow loader from YAML."""

import os
import tempfile

import pytest
import yaml
from runtime.models import TaskGraph, WorkflowDefinition
from runtime.workflow import (
    WorkflowLoadError,
    WorkflowRegistry,
    load_workflow_from_dict,
    load_workflow_from_yaml,
)


# ─── Fixtures ────────────────────────────────────────────────────────────


RESEARCH_WORKFLOW_YAML = """
name: investment-research
version: "2.0.0"
description: End-to-end investment research workflow

nodes:
  - id: planner
    label: "Planner"
    skill: planner
    timeout: 30

  - id: data
    label: "Data Collection"
    skill: data-collector
    timeout: 60

  - id: fundamental
    label: "Fundamental Analysis"
    skill: fundamental-analysis
    timeout: 120

  - id: technical
    label: "Technical Analysis"
    skill: technical-analysis
    timeout: 120

  - id: portfolio
    label: "Portfolio Selection"
    skill: portfolio-selection
    timeout: 60

  - id: report
    label: "Report"
    skill: report-generator
    timeout: 30

edges:
  - from: planner
    to: data
  - from: data
    to: [fundamental, technical]
  - from: fundamental
    to: portfolio
  - from: technical
    to: portfolio
  - from: portfolio
    to: report

entry_points: [planner]
output_nodes: [report]
"""


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory with workflow files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write research workflow
        with open(os.path.join(tmpdir, "research.yaml"), "w") as f:
            f.write(RESEARCH_WORKFLOW_YAML)

        # Write a simple test workflow
        simple_yaml = """
name: simple-test
version: "1.0.0"
description: Simple linear test

nodes:
  - id: a
    label: "A"
    skill: skill_a
  - id: b
    label: "B"
    skill: skill_b

edges:
  - from: a
    to: b

entry_points: [a]
output_nodes: [b]
"""
        with open(os.path.join(tmpdir, "simple.yaml"), "w") as f:
            f.write(simple_yaml)

        yield tmpdir


# ─── load_workflow_from_dict Tests ──────────────────────────────────────


class TestLoadWorkflowFromDict:
    def test_basic_workflow(self):
        data = yaml.safe_load(RESEARCH_WORKFLOW_YAML)
        wf = load_workflow_from_dict(data)

        assert isinstance(wf, WorkflowDefinition)
        assert wf.name == "investment-research"
        assert wf.version == "2.0.0"
        assert isinstance(wf.graph, TaskGraph)
        assert len(wf.graph.nodes) == 6

    def test_graph_structure(self):
        data = yaml.safe_load(RESEARCH_WORKFLOW_YAML)
        wf = load_workflow_from_dict(data)

        graph = wf.graph
        # Check nodes
        assert "planner" in graph.nodes
        assert "fundamental" in graph.nodes
        assert "technical" in graph.nodes
        assert "portfolio" in graph.nodes

        # Check edges
        edge_pairs = [(e.source_id, e.target_id) for e in graph.edges]
        assert ("planner", "data") in edge_pairs
        assert ("fundamental", "portfolio") in edge_pairs

        # Check entry points and output nodes
        assert graph.entry_points == ["planner"]
        assert graph.output_nodes == ["report"]

    def test_missing_name(self):
        with pytest.raises(WorkflowLoadError, match="name"):
            load_workflow_from_dict({"nodes": [], "edges": []})

    def test_missing_nodes(self):
        with pytest.raises(WorkflowLoadError, match="no nodes"):
            load_workflow_from_dict({"name": "test", "nodes": []})

    def test_multi_target_edge(self):
        """When 'to' is a list, multiple edges should be created."""
        data = yaml.safe_load(RESEARCH_WORKFLOW_YAML)
        wf = load_workflow_from_dict(data)

        edge_pairs = [(e.source_id, e.target_id) for e in wf.graph.edges]
        assert ("data", "fundamental") in edge_pairs
        assert ("data", "technical") in edge_pairs

    def test_global_config_applied(self):
        """Global config should be applied to nodes that don't specify their own."""
        yaml_text = """
name: config-test
version: "1.0.0"
config:
  default_timeout: 45
  max_retries: 3

nodes:
  - id: a
    label: "A"
    skill: skill_a
    # no timeout specified → should use default_timeout

  - id: b
    label: "B"
    skill: skill_b
    timeout: 99  # explicit timeout → keep

edges:
  - from: a
    to: b
"""
        data = yaml.safe_load(yaml_text)
        wf = load_workflow_from_dict(data)

        assert wf.graph.nodes["a"].config.timeout == 45
        assert wf.graph.nodes["b"].config.timeout == 99
        assert wf.graph.nodes["a"].config.max_retries == 3


# ─── load_workflow_from_yaml Tests ──────────────────────────────────────


class TestLoadWorkflowFromYaml:
    def test_load_from_file(self, temp_workflow_dir):
        filepath = os.path.join(temp_workflow_dir, "research.yaml")
        wf = load_workflow_from_yaml(filepath)

        assert wf.name == "investment-research"
        assert len(wf.graph.nodes) == 6

    def test_file_not_found(self):
        with pytest.raises(WorkflowLoadError, match="not found"):
            load_workflow_from_yaml("/nonexistent/path.yaml")

    def test_invalid_yaml(self, temp_workflow_dir):
        """Invalid YAML should raise an error."""
        filepath = os.path.join(temp_workflow_dir, "invalid.yaml")
        with open(filepath, "w") as f:
            f.write("invalid: [unclosed: bracket")

        with pytest.raises(Exception):
            load_workflow_from_yaml(filepath)


# ─── WorkflowRegistry Tests ──────────────────────────────────────────────


class TestWorkflowRegistry:
    def test_load_all(self, temp_workflow_dir):
        registry = WorkflowRegistry(temp_workflow_dir)
        assert registry.count == 2

    def test_get_by_name(self, temp_workflow_dir):
        registry = WorkflowRegistry(temp_workflow_dir)
        wf = registry.get("simple-test")
        assert wf is not None
        assert wf.name == "simple-test"

    def test_get_nonexistent(self, temp_workflow_dir):
        registry = WorkflowRegistry(temp_workflow_dir)
        assert registry.get("nonexistent") is None

    def test_get_graph(self, temp_workflow_dir):
        registry = WorkflowRegistry(temp_workflow_dir)
        graph = registry.get_graph("simple-test")
        assert isinstance(graph, TaskGraph)
        assert "a" in graph.nodes

    def test_list(self, temp_workflow_dir):
        registry = WorkflowRegistry(temp_workflow_dir)
        workflows = registry.list()
        assert len(workflows) == 2
        names = {w.name for w in workflows}
        assert names == {"investment-research", "simple-test"}

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = WorkflowRegistry(tmpdir)
            assert registry.count == 0
            assert registry.list() == []

    def test_reload(self, temp_workflow_dir):
        registry = WorkflowRegistry(temp_workflow_dir)
        assert registry.count == 2

        # Add a new workflow
        new_yaml = """
name: new-wf
version: "1.0.0"
nodes:
  - id: x
    label: "X"
    skill: skill_x
edges: []
"""
        with open(os.path.join(temp_workflow_dir, "new.yaml"), "w") as f:
            f.write(new_yaml)

        registry.reload()
        assert registry.count == 3
        assert registry.get("new-wf") is not None

    def test_invalid_file_is_skipped(self, temp_workflow_dir):
        """A workflow file that fails to parse should be skipped with a warning."""
        with open(os.path.join(temp_workflow_dir, "bad.yaml"), "w") as f:
            f.write("name: bad\nnodes: []\n")  # empty nodes will fail

        # Should not raise — just skip
        registry = WorkflowRegistry(temp_workflow_dir)
        assert registry.get("bad") is None
