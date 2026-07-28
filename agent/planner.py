# Agent Planner — Requirement decomposition into analysis plan

from strategies.base.models import AnalysisPlan, AnalysisStep


class Planner:
    """Decomposes user investment requirements into structured analysis plans."""

    async def create_plan(
        self,
        user_requirement: str,
        available_skills: list[dict],
    ) -> AnalysisPlan:
        """Parse user requirement and produce an analysis plan.

        Uses the LLM to understand the user's intent, desired strategy
        weights, risk preference, and data needs. Returns a structured
        plan the Executor can follow.
        """
        # TODO: Implement LLM-based requirement decomposition
        # 1. Classify investment style (value/growth/momentum/dividend/mixed)
        # 2. Determine risk preference from language cues
        # 3. Assign strategy weights based on style
        # 4. List data requirements
        # 5. Generate ordered analysis steps with dependencies
        # 6. Return structured AnalysisPlan

        raise NotImplementedError

    async def adjust_plan(
        self,
        plan: AnalysisPlan,
        feedback: str,
    ) -> AnalysisPlan:
        """Adjust an existing plan based on user feedback."""
        raise NotImplementedError
