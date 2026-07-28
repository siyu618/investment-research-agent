# Agent Executor — Executes analysis plans by invoking skills and MCP tools

from strategies.base.models import (
    AnalysisPlan,
    AnalysisContext,
    AnalysisResult,
    MemoryAccess,
)
from agent.memory import MemoryManager


class Executor:
    """Carries out the analysis plan step by step.

    For each step in the plan:
      1. Load the appropriate skill from the registry
      2. Prepare the analysis context (stock data, financials, prices)
      3. Call MCP tools to collect data if needed
      4. Invoke the skill's analyze() method
      5. Store intermediate results in working memory

    Handles retries, step failures, and partial results.
    """

    def __init__(self, memory: MemoryManager, mcp_client=None):
        self.memory = memory
        self.mcp_client = mcp_client
        self._step_results: dict[int, AnalysisResult] = {}

    async def execute_plan(self, plan: AnalysisPlan) -> dict[int, AnalysisResult]:
        """Execute all steps in the analysis plan.

        Respects step dependencies. Independent steps may run in parallel.
        Failed steps are retried (max 2). Non-critical failures log and continue.
        """
        # TODO: Implement step execution loop
        # 1. Topological sort by dependencies
        # 2. For each step (or parallel batch):
        #    a. Load skill by name
        #    b. Collect required data via MCP tools
        #    c. Build AnalysisContext
        #    d. Call skill.analyze(context)
        #    e. Store result in working memory
        # 3. Handle failures: retry or skip
        # 4. Return all results
        raise NotImplementedError

    async def collect_data(self, requirements: list[str], stocks: list[str]) -> dict:
        """Collect market data via MCP tools for the analysis.

        Uses caching to avoid redundant API calls within a session.
        """
        raise NotImplementedError
