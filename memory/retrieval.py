# Knowledge Retriever — RAG layer over the ResearchMemory tier
#
# Turns the research memory tier into a queryable knowledge layer for the
# agent: prior research is recalled by company / industry / theme and injected
# into the current run, so re-analyzing a stock (or a sector) builds on what
# was learned before instead of starting from scratch.
#
# The retriever emits a real `kind="retrieval"` trace span for observability:
#   User Query → Planner → Agent → Tool → Retrieval → LLM → Final Result
#
# Entities are extracted from the user's goal by convention:
#   - a ts_code (600519.SH)       → company subject
#   - an industry/theme keyword   → industry/theme subject (best-effort)

from __future__ import annotations

import logging
import re
from typing import Any

from memory.research import ResearchMemory
from runtime.tracing.trace_span import trace_span

logger = logging.getLogger("memory.retrieval")

# Knowledge subjects that the ResearchMemory tier indexes (see research.py).
_SUBJECT_TYPES = ("company", "industry", "theme")

# Industry/theme keyword → subject. Small seed map; expands as research is
# stored. A miss simply recalls nothing — it does not fail the run.
_INDUSTRY_KEYWORDS: dict[str, str] = {
    "白酒": "industry:白酒",
    "酒": "industry:白酒",
    "医药": "industry:医药",
    "银行": "industry:银行",
    "券商": "industry:券商",
    "半导体": "industry:半导体",
    "新能源": "theme:新能源",
    "人工智能": "theme:AI",
    "AI": "theme:AI",
    "机器人": "theme:机器人",
}


class KnowledgeRetriever:
    """Recalls prior research from the knowledge layer for a user goal.

    Usage:
        retriever = KnowledgeRetriever(ResearchMemory(db_path="memory/research.db"))
        ctx = await retriever.recall(goal, limit=5, span_sink=[])
        # ctx["retrieval_results"] = [...], ctx["retrieval_entities"] = [...]
    """

    def __init__(self, memory: ResearchMemory | None = None):
        self.memory = memory or ResearchMemory()

    # ─── Recall ─────────────────────────────────────────────────────────

    async def recall(
        self,
        goal: str,
        limit: int = 5,
        span_sink: list[dict] | None = None,
    ) -> dict:
        """Recall prior research relevant to the user goal.

        Returns a context dict the runtime merges into the task context:
            {
              "retrieval_results": [MemoryEntry ...],
              "retrieval_entities": [ {subject_type, subject}, ... ],
              "retrieval_count": int,
            }
        """
        entities = self._extract_entities(goal)
        if not entities:
            return {
                "retrieval_results": [],
                "retrieval_entities": [],
                "retrieval_count": 0,
            }

        results: list[Any] = []
        for subj_type, subject in entities:
            # Record a real retrieval span per subject (observability).
            async with trace_span(
                "retrieval", "retrieval", "retrieval", f"retrieve:{subject}",
                sink=span_sink,
            ) as span:
                span.set_input({"subject_type": subj_type, "subject": subject,
                                "limit": limit})
                try:
                    hits = await self.memory.get_by_subject(subj_type, subject, limit)
                    span.set_output({"hits": len(hits)})
                    if not hits:
                        span.status = "empty"
                    results.extend(hits)
                except Exception as e:
                    span.status = "error"
                    span.error = str(e)[:200]
                    logger.warning("Retrieval failed for %s:%s — %s",
                                   subj_type, subject, e)

        # Dedup by key, newest first (the tier returns newest-first per query).
        seen: set[str] = set()
        deduped = []
        for r in results:
            if r.key in seen:
                continue
            seen.add(r.key)
            deduped.append(r)
        deduped = deduped[:limit]

        return {
            "retrieval_results": deduped,
            "retrieval_entities": [{"subject_type": t, "subject": s}
                                   for t, s in entities],
            "retrieval_count": len(deduped),
        }

    # ─── Persist ────────────────────────────────────────────────────────

    async def store_result(
        self,
        *,
        key: str,
        company: str,
        industry: str = "",
        theme: str = "",
        score: float,
        reasoning: str = "",
        strategy: str = "",
        span_sink: list[dict] | None = None,
    ) -> None:
        """Persist a completed analysis back into the knowledge layer.

        The stored entry is tagged with company (required) and, when known,
        industry/theme — so later runs on the same company/industry/theme
        recall it (cross-session knowledge accumulation).
        """
        value: dict[str, Any] = {
            "company": company,
            "score": score,
            "reasoning": reasoning,
            "strategy": strategy,
        }
        # A research result belongs to BOTH its company and its industry/
        # theme. ResearchMemory tags `subject_type:subject` plus the company
        # code, so later runs recall it via either axis.
        if industry:
            value["industry"] = industry
            value["subject_type"] = "industry"
            value["subject"] = industry
        elif theme:
            value["subject_type"] = "theme"
            value["subject"] = theme
        else:
            value["subject_type"] = "company"
            value["subject"] = company
        value["tags"] = [f"company:{company}"]

        async with trace_span(
            "retrieval", "retrieval", "retrieval", f"store:{company}",
            sink=span_sink,
        ) as span:
            span.set_input({"key": key, "company": company})
            try:
                await self.memory.store(key, value)
                span.set_output({"stored": True})
            except Exception as e:
                span.status = "error"
                span.error = str(e)[:200]

    # ─── Entity extraction ──────────────────────────────────────────────

    @staticmethod
    def _extract_entities(goal: str) -> list[tuple[str, str]]:
        """Extract (subject_type, subject) pairs from a user goal."""
        entities: list[tuple[str, str]] = []
        # 1. Explicit ts_code → company
        for m in re.finditer(r"\b(\d{6}\.(SH|SZ|BJ))\b", goal, re.IGNORECASE):
            code = m.group(1).upper()
            entities.append(("company", code))
        # 2. Known industry/theme keyword → subject
        for keyword, subject in _INDUSTRY_KEYWORDS.items():
            if keyword in goal:
                subj_type, _, name = subject.partition(":")
                entities.append((subj_type, name))
                break  # first match is enough for a subject
        # Dedup while preserving order
        seen: set[tuple[str, str]] = set()
        deduped = []
        for e in entities:
            if e in seen:
                continue
            seen.add(e)
            deduped.append(e)
        return deduped
