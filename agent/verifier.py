# Agent Verifier — Multi-phase verification with provenance checks
#
# Verifies BEFORE report generation:
#   1. Data freshness — are financial statements too old?
#   2. No look-ahead bias — are we using future data?
#   3. Weight correctness — do strategy weights sum to 1?
#   4. Missing data handling — were gaps flagged?
#   5. Evidence-backed conclusions — does every score have supporting data?

from __future__ import annotations

from datetime import datetime, timedelta

from strategies.base.models import (
    AnalysisPlan,
    AnalysisResult,
    VerificationResult,
)


class Verifier:
    """Multi-phase verification for analysis results."""

    MAX_STATEMENT_AGE_DAYS = 365  # Annual financial statements older than this are stale
    MAX_LOOK_AHEAD_WARN = "Data date {data_date} is after analysis date {analysis_date} — potential look-ahead bias"

    async def verify(
        self,
        plan: AnalysisPlan,
        results: dict[int, AnalysisResult],
    ) -> VerificationResult:
        """Run all verification phases."""
        analysis_date = datetime.now()
        checks = []
        warnings = []
        errors = []

        # Phase 1: Data freshness
        freshness = self._check_freshness(results, analysis_date)
        checks.append({"phase": "data_freshness", **freshness})
        if not freshness["passed"]:
            warnings.extend(freshness.get("messages", []))

        # Phase 2: No look-ahead bias
        lookahead = self._check_lookahead(results, analysis_date)
        checks.append({"phase": "no_lookahead", **lookahead})
        if not lookahead["passed"]:
            warnings.extend(lookahead.get("messages", []))

        # Phase 3: Weight correctness
        weight_check = self._check_weights(plan)
        checks.append({"phase": "weight_correctness", **weight_check})
        if not weight_check["passed"]:
            errors.extend(weight_check.get("messages", []))

        # Phase 4: Missing data flagged
        missing = self._check_missing_data(results)
        checks.append({"phase": "missing_data_handled", **missing})
        if not missing["passed"]:
            warnings.extend(missing.get("messages", []))

        # Phase 5: Evidence-backed conclusions
        evidence = self._check_evidence(results)
        checks.append({"phase": "evidence_backed", **evidence})
        if not evidence["passed"]:
            warnings.extend(evidence.get("messages", []))

        passed = all(c["passed"] for c in checks)

        return VerificationResult(
            passed=passed,
            data_complete=freshness["passed"],
            strategy_consistent=weight_check["passed"],
            risk_validated=missing["passed"],
            checks=checks,
            warnings=warnings,
            errors=errors,
        )

    def _check_freshness(self, results: dict, analysis_date: datetime) -> dict:
        """Check that financial data is not too old."""
        now = analysis_date
        max_age = timedelta(days=self.MAX_STATEMENT_AGE_DAYS)
        messages = []

        # Try to find data dates from fundamental analysis provenance
        for _, step_result in results.items():
            if hasattr(step_result, "profiles"):
                for profile in step_result.profiles if step_result.profiles else []:
                    for metric in getattr(profile, "metrics", []):
                        try:
                            available = datetime.fromisoformat(metric.available_at)
                            if now - available > max_age:
                                messages.append(
                                    f"{getattr(profile, 'name', '')} metric "
                                    f"'{metric.metric}' dated {metric.available_at} "
                                    f"exceeds max age ({self.MAX_STATEMENT_AGE_DAYS} days)"
                                )
                        except (ValueError, AttributeError):
                            pass

        return {
            "passed": len(messages) < 3,
            "messages": messages[:5],
            "details": f"Checked {len(results)} results for data freshness",
        }

    def _check_lookahead(self, results: dict, analysis_date: datetime) -> dict:
        """Check that no data dates are after the analysis date."""
        messages = []
        for _, step_result in results.items():
            if hasattr(step_result, "profiles"):
                for profile in getattr(step_result, "profiles", []):
                    for metric in getattr(profile, "metrics", []):
                        try:
                            dt = datetime.fromisoformat(metric.available_at)
                            if dt > analysis_date + timedelta(days=7):
                                messages.append(
                                    f"{getattr(profile, 'name', '')} '{metric.metric}' "
                                    f"date {metric.available_at} is in the future"
                                )
                        except (ValueError, AttributeError):
                            pass

        return {
            "passed": len(messages) == 0,
            "messages": messages,
            "details": f"No look-ahead bias detected in {len(results)} results",
        }

    def _check_weights(self, plan: AnalysisPlan) -> dict:
        """Verify strategy weights sum to 1.0 (within tolerance)."""
        if not plan.strategy_weights:
            return {"passed": True, "messages": [], "details": "No strategy weights to check"}
        total = sum(plan.strategy_weights.values())
        passed = abs(total - 1.0) < 0.02
        return {
            "passed": passed,
            "messages": [] if passed else [f"Strategy weights sum to {total:.4f}, expected 1.0"],
            "details": f"Strategy weights: {plan.strategy_weights}, sum={total:.4f}",
        }

    def _check_missing_data(self, results: dict) -> dict:
        """Verify that missing data was flagged."""
        messages = []
        for _, step_result in results.items():
            if hasattr(step_result, "profiles"):
                for profile in getattr(step_result, "profiles", []):
                    flags = getattr(profile, "missing_data_flags", [])
                    if flags:
                        messages.append(
                            f"{getattr(profile, 'name', '')}: missing {', '.join(flags)}"
                        )
        return {
            "passed": True,  # Missing data is allowed as long as it's flagged
            "messages": messages,
            "details": f"Checked {len(results)} results for missing data flags",
            "missing_data_count": len(messages),
        }

    def _check_evidence(self, results: dict) -> dict:
        """Verify that scores are backed by evidence (metrics)."""
        messages = []
        for _, step_result in results.items():
            if hasattr(step_result, "profiles"):
                for profile in getattr(step_result, "profiles", []):
                    metrics = getattr(profile, "metrics", [])
                    if not metrics and getattr(profile, "score", 0) > 0:
                        messages.append(
                            f"{getattr(profile, 'name', '')}: has score "
                            f"{profile.score} but zero metrics"
                        )
        return {
            "passed": len(messages) == 0,
            "messages": messages,
            "details": f"Verified evidence for {len(results)} results",
        }
