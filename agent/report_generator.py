# Agent Report Generator — Produces structured investment research reports

from datetime import datetime
from typing import Optional

from strategies.base.models import (
    AnalysisPlan,
    AnalysisResult,
    InvestmentReport,
    VerificationResult,
)


class ReportGenerator:
    """Generates structured investment research reports from analysis results.

    Uses template-based assembly with sections for market overview,
    candidate selection, strategy scores, detailed analysis, risk assessment,
    portfolio suggestions, and disclaimer.
    """

    DISCLAIMER = (
        "This report is AI-generated for reference only. "
        "It does not constitute investment advice. "
        "Past performance is not indicative of future results. "
        "Always conduct your own research before making investment decisions. "
        "Data source: Tushare Financial Data API."
    )

    def __init__(self, agent_version: str = "1.0.0"):
        self.agent_version = agent_version

    async def generate(
        self,
        plan: AnalysisPlan,
        results: dict[int, AnalysisResult],
        verification: VerificationResult,
    ) -> InvestmentReport:
        """Generate a complete investment research report."""
        # Build market overview from collected data
        market_overview = self._build_market_overview(results)

        # Extract candidate analyses (from portfolio-selection step & individual skills)
        candidates = self._extract_candidates(results)

        # Build portfolio suggestion
        portfolio_suggestion = self._build_portfolio_suggestion(results)

        report = InvestmentReport(
            report_id=f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            agent_version=self.agent_version,
            user_requirement=plan.objective,
            market_overview=market_overview,
            candidates=candidates,
            portfolio_suggestion=portfolio_suggestion,
            disclaimer=self.DISCLAIMER,
        )

        return report

    def _build_market_overview(
        self, results: dict[int, AnalysisResult]
    ) -> str:
        """Build market overview section."""
        # TODO: Aggregate market data context into narrative
        return "Market overview analysis (stub)"

    def _extract_candidates(
        self, results: dict[int, AnalysisResult]
    ) -> list[AnalysisResult]:
        """Extract candidate stock analyses from results."""
        # Return all individual stock analyses
        return list(results.values())

    def _build_portfolio_suggestion(
        self, results: dict[int, AnalysisResult]
    ) -> str:
        """Build portfolio suggestion section."""
        # TODO: Combine scores and provide allocation suggestions
        return "Portfolio suggestion (stub)"

    def format_markdown(self, report: InvestmentReport) -> str:
        """Format the report as readable markdown."""
        lines = [
            f"# Investment Research Report",
            f"",
            f"**Report ID:** {report.report_id}",
            f"**Generated:** {report.created_at}",
            f"**Agent Version:** {report.agent_version}",
            f"",
            f"---",
            f"",
            f"## 1. User Requirement",
            f"",
            f"{report.user_requirement}",
            f"",
            f"## 2. Market Overview",
            f"",
            f"{report.market_overview}",
            f"",
            f"## 3. Candidate Analysis",
            f"",
        ]

        for i, candidate in enumerate(report.candidates, 1):
            lines.extend([
                f"### {i}. {candidate.skill_name} Score: {candidate.score:.2f}",
                f"",
                f"- **Confidence:** {candidate.confidence:.2f}",
                f"- **Reasoning:** {candidate.reasoning}",
                f"- **Risk Factors:**",
            ])
            for risk in candidate.risk_factors:
                lines.append(f"  - [{risk.severity.value}] {risk.category}: {risk.description}")
            if candidate.warnings:
                lines.append(f"- **Warnings:**")
                for w in candidate.warnings:
                    lines.append(f"  - {w}")
            lines.append("")

        lines.extend([
            f"## 4. Portfolio Suggestion",
            f"",
            f"{report.portfolio_suggestion}",
            f"",
            f"---",
            f"",
            f"## Disclaimer",
            f"",
            f"{report.disclaimer}",
            f"",
        ])

        return "\n".join(lines)
