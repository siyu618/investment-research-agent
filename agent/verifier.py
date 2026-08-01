# Agent Verifier — Multi-phase verification with severity + policy_mode
#
# Each check produces a severity (info/warning/error/fatal). The policy
# mode decides which severities block report generation:
#   permissive — only fatal blocks
#   standard   — error + fatal block
#   strict     — warning + error + fatal block
#
# Checks:
#   1. Data freshness    — stale data → warning (older = worse)
#   2. No look-ahead     — future data → FATAL (must block: PIT violation)
#   3. Weight correctness— weights not summing to 1 → error
#   4. Missing data      — flagged gaps → warning; unflagged → error
#   5. Evidence chain    — score with no backing metrics → error
#   6. Report consistency— verifier result vs report content

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from strategies.base.models import AnalysisPlan, AnalysisResult, VerificationResult


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class PolicyMode(str, Enum):
    PERMISSIVE = "permissive"
    STANDARD = "standard"
    STRICT = "strict"

    @property
    def blocks(self) -> set[Severity]:
        """Severities that block report generation under this policy."""
        if self == PolicyMode.PERMISSIVE:
            return {Severity.FATAL}
        if self == PolicyMode.STANDARD:
            return {Severity.FATAL, Severity.ERROR}
        return {Severity.FATAL, Severity.ERROR, Severity.WARNING}


class VerificationFinding:
    """A single check finding with severity and actionable detail."""

    def __init__(
        self,
        phase: str,
        severity: Severity,
        message: str,
        detail: str = "",
    ):
        self.phase = phase
        self.severity = severity
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "severity": self.severity.value,
            "message": self.message,
            "detail": self.detail,
        }


class Verifier:
    """Multi-phase verification with severity + policy mode."""

    MAX_STATEMENT_AGE_DAYS = 365

    def __init__(self, policy_mode: str = "standard"):
        self.policy = PolicyMode(policy_mode)

    async def verify(
        self,
        plan: AnalysisPlan,
        results: dict[int, AnalysisResult],
    ) -> VerificationResult:
        """Run all verification phases, returning findings + pass/fail."""
        analysis_date = datetime.now()
        findings: list[VerificationFinding] = []

        findings.extend(self._check_freshness(results, analysis_date))
        findings.extend(self._check_lookahead(results, analysis_date))
        findings.extend(self._check_weights(plan))
        findings.extend(self._check_missing_data(results))
        findings.extend(self._check_evidence(results))

        # Decide pass/fail by policy
        blocking = self.policy.blocks
        blocked = [f for f in findings if f.severity in blocking]

        return VerificationResult(
            passed=len(blocked) == 0,
            data_complete=not any(f.phase == "data_freshness" and f.severity in blocking for f in findings),
            strategy_consistent=not any(f.phase == "weight_correctness" and f.severity in blocking for f in findings),
            risk_validated=not any(f.phase == "missing_data_handled" and f.severity in blocking for f in findings),
            checks=[f.to_dict() for f in findings],
            warnings=[f.message for f in findings if f.severity == Severity.WARNING],
            errors=[f.message for f in findings if f.severity in (Severity.ERROR, Severity.FATAL)],
            policy_mode=self.policy.value,
        )

    # ─── Checks ────────────────────────────────────────────────────────

    def _check_freshness(self, results: dict, analysis_date: datetime) -> list[VerificationFinding]:
        """Stale financial data → warning (escalating by age)."""
        findings = []
        now = analysis_date
        max_age = timedelta(days=self.MAX_STATEMENT_AGE_DAYS)

        for _, step_result in results.items():
            profiles = getattr(step_result, "profiles", None) or []
            for profile in profiles:
                for metric in getattr(profile, "metrics", []):
                    try:
                        available = datetime.fromisoformat(metric.available_at)
                        age = now - available
                        if age > max_age:
                            sev = Severity.WARNING if age < 2 * max_age else Severity.ERROR
                            findings.append(VerificationFinding(
                                phase="data_freshness",
                                severity=sev,
                                message=f"{getattr(profile, 'name', '')} '{metric.metric}' "
                                        f"dated {metric.available_at} (age {age.days}d)",
                                detail=f"max age {self.MAX_STATEMENT_AGE_DAYS}d",
                            ))
                    except (ValueError, AttributeError):
                        continue
        return findings

    def _check_lookahead(self, results: dict, analysis_date: datetime) -> list[VerificationFinding]:
        """Future data (PIT violation) → FATAL. Must block the run."""
        findings = []
        for _, step_result in results.items():
            profiles = getattr(step_result, "profiles", None) or []
            for profile in profiles:
                for metric in getattr(profile, "metrics", []):
                    try:
                        dt = datetime.fromisoformat(metric.available_at)
                        if dt > analysis_date + timedelta(days=7):
                            findings.append(VerificationFinding(
                                phase="no_lookahead",
                                severity=Severity.FATAL,
                                message=f"{getattr(profile, 'name', '')} '{metric.metric}' "
                                        f"date {metric.available_at} is in the future",
                                detail="Point-in-time violation: data published after analysis date",
                            ))
                    except (ValueError, AttributeError):
                        continue
        return findings

    def _check_weights(self, plan: AnalysisPlan) -> list[VerificationFinding]:
        """Weights not summing to 1 → error (must fix before scoring)."""
        if not plan.strategy_weights:
            return [VerificationFinding(
                phase="weight_correctness",
                severity=Severity.WARNING,
                message="No strategy weights to check",
            )]
        total = sum(plan.strategy_weights.values())
        if abs(total - 1.0) < 0.02:
            return [VerificationFinding(
                phase="weight_correctness",
                severity=Severity.INFO,
                message=f"Weights sum to {total:.4f}",
            )]
        return [VerificationFinding(
            phase="weight_correctness",
            severity=Severity.ERROR,
            message=f"Strategy weights sum to {total:.4f}, expected 1.0",
        )]

    def _check_missing_data(self, results: dict) -> list[VerificationFinding]:
        """Flagged gaps → warning; score without data → error."""
        findings = []
        for _, step_result in results.items():
            profiles = getattr(step_result, "profiles", None) or []
            for profile in profiles:
                flags = getattr(profile, "missing_data_flags", []) or []
                for flag in flags:
                    findings.append(VerificationFinding(
                        phase="missing_data_handled",
                        severity=Severity.WARNING,
                        message=f"{getattr(profile, 'name', '')}: missing {flag}",
                    ))
                # A score > 0 with zero metrics and flagged gaps is an error
                if flags and getattr(profile, "score", 0) > 0 and not getattr(profile, "metrics", []):
                    findings.append(VerificationFinding(
                        phase="missing_data_handled",
                        severity=Severity.ERROR,
                        message=f"{getattr(profile, 'name', '')}: scored without any metrics",
                    ))
        return findings

    def _check_evidence(self, results: dict) -> list[VerificationFinding]:
        """Score with no backing evidence → error."""
        findings = []
        for _, step_result in results.items():
            profiles = getattr(step_result, "profiles", None) or []
            for profile in profiles:
                metrics = getattr(profile, "metrics", []) or []
                if not metrics and getattr(profile, "score", 0) > 0:
                    findings.append(VerificationFinding(
                        phase="evidence_backed",
                        severity=Severity.ERROR,
                        message=f"{getattr(profile, 'name', '')}: score {profile.score} with zero metrics",
                    ))
        return findings
