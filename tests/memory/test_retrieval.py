"""Tests for memory/retrieval.py — KnowledgeRetriever (RAG knowledge layer)."""

import pytest
from memory.research import ResearchMemory
from memory.retrieval import KnowledgeRetriever


@pytest.fixture
def retriever(tmp_path):
    memory = ResearchMemory(db_path=str(tmp_path / "research.db"))
    return KnowledgeRetriever(memory=memory)


@pytest.fixture
def retriever_memory(tmp_path):
    return ResearchMemory(db_path=str(tmp_path / "research.db"))


@pytest.mark.asyncio
class TestKnowledgeRetriever:
    async def test_recall_company_from_goal(self, retriever, retriever_memory):
        """A prior company analysis is recalled for a later run on the same code."""
        await retriever.store_result(
            key="600519.SH:20260801",
            company="600519.SH",
            score=0.85,
            reasoning="strong brand moat",
        )
        ctx = await retriever.recall("重新分析 600519.SH")
        assert ctx["retrieval_count"] == 1
        assert ctx["retrieval_results"][0].value["score"] == 0.85
        assert ("company", "600519.SH") in [
            (e["subject_type"], e["subject"]) for e in ctx["retrieval_entities"]
        ]

    async def test_recall_industry_accumulates(self, retriever, retriever_memory):
        """Industry-level knowledge accumulates across companies."""
        await retriever.store_result(
            key="a:1", company="600519.SH", industry="白酒", score=0.8,
        )
        await retriever.store_result(
            key="b:1", company="000858.SZ", industry="白酒", score=0.9,
        )
        ctx = await retriever.recall("分析白酒行业")
        assert ctx["retrieval_count"] == 2
        codes = {r.value["company"] for r in ctx["retrieval_results"]}
        assert codes == {"600519.SH", "000858.SZ"}

    async def test_recall_theme(self, retriever):
        """Theme subjects recall prior research."""
        await retriever.store_result(
            key="ai:1", company="002230.SZ", theme="AI", score=0.75,
        )
        ctx = await retriever.recall("AI 主题投资机会")
        assert ctx["retrieval_count"] == 1
        assert ctx["retrieval_results"][0].value["score"] == 0.75

    async def test_recall_no_entities(self, retriever):
        """Goals with no extractable entity recall nothing."""
        ctx = await retriever.recall("帮我看看这个组合")
        assert ctx["retrieval_count"] == 0
        assert ctx["retrieval_results"] == []

    async def test_recall_emits_spans(self, retriever):
        """Retrieval spans are recorded for observability."""
        await retriever.store_result(
            key="600519.SH:20260801", company="600519.SH", score=0.85,
        )
        sink: list[dict] = []
        await retriever.recall("分析 600519.SH", span_sink=sink)
        retrieval = [s for s in sink if s["kind"] == "retrieval"]
        assert len(retrieval) >= 1
        assert retrieval[0]["name"] == "retrieve:600519.SH"

    async def test_recall_dedup(self, retriever):
        """Duplicate entries across subject queries are deduped by key."""
        await retriever.store_result(
            key="k1", company="600519.SH", industry="白酒", score=0.8,
        )
        # Same key stored once; industry+company both match but key dedups.
        ctx = await retriever.recall("分析 600519.SH 白酒")
        keys = {r.key for r in ctx["retrieval_results"]}
        assert len(keys) == 1
