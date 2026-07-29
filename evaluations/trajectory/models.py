# Trajectory Evaluation — Scoring Models
#
# Data models for representing trajectory evaluation scores.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TrajectoryExpectations:
    """Expected metrics for a trajectory evaluation.

    Loaded from YAML evaluation case definitions.
    """
    optimal_node_count: int = -1
    optimal_tool_call_count: int = -1
    expected_duration_ms: int = -1
    expected_retry_count: int = 0
    required_events: list[str] = field(default_factory=list)
    forbidden_events: list[str] = field(default_factory=list)


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""
    name: str
    score: float                # 0.0 - 100.0
    weight: float               # 0.0 - 1.0 (sums to 1.0)
    description: str = ""
    criteria_met: list[str] = field(default_factory=list)
    criteria_missed: list[str] = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class TrajectoryScore:
    """Aggregate trajectory evaluation result for a single run."""
    session_id: str = ""
    case_id: str = ""
    overall_score: float = 0.0    # 0.0 - 100.0
    passed: bool = True
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    exceptions: list[str] = field(default_factory=list)
    run_duration_ms: int = 0
    evaluated_at: str = field(default_factory=lambda: datetime.now().isoformat())
