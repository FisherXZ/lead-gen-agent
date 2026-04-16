"""Tests for cross-project evidence sharing in batch research."""

import asyncio
from unittest.mock import AsyncMock, patch

from src.evidence import EvidenceStore
from src.models import AgentResult, Finding, ReflectionResult


# ---------------------------------------------------------------------------
# EvidenceStore thread safety
# ---------------------------------------------------------------------------


class TestEvidenceStoreAsyncAdd:
    async def test_add_async_dedups(self):
        store = EvidenceStore()
        f1 = Finding(
            text="McCarthy EPC",
            source_url="https://example.com/pr",
            source_tool="tavily_search",
            iteration=1,
        )
        f2 = Finding(
            text="McCarthy EPC duplicate",
            source_url="https://example.com/pr",
            source_tool="brave_search",
            iteration=2,
        )
        assert await store.add_async(f1) is True
        assert await store.add_async(f2) is False  # dedup
        assert len(store.findings) == 1

    async def test_add_async_concurrent_safe(self):
        """Concurrent add_async calls don't corrupt the store."""
        store = EvidenceStore()

        async def add_many(prefix: str):
            for i in range(20):
                await store.add_async(Finding(
                    text=f"{prefix} {i}",
                    source_url=f"https://example.com/{prefix}/{i}",
                    source_tool="tavily_search",
                    iteration=i,
                ))

        # Run 3 producers concurrently
        await asyncio.gather(add_many("a"), add_many("b"), add_many("c"))
        assert len(store.findings) == 60
        assert len(store.visited_urls) == 60


# ---------------------------------------------------------------------------
# Shared findings seeding and propagation
# ---------------------------------------------------------------------------


def _sample_project(pid="p1"):
    return {
        "id": pid,
        "project_name": f"Project {pid}",
        "queue_id": f"Q-{pid}",
        "developer": "NextEra Energy",
        "mw_capacity": 200,
        "state": "TX",
        "iso_region": "ERCOT",
    }


class TestSharedFindingsSeeding:
    """Verify that shared_findings seeds a project's local evidence store."""

    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_shared_findings_visible_to_reflection(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth
    ):
        """Evidence from shared store is seeded and logged in v3 orchestrator."""
        from src.research import run_research

        # Pre-populate shared store (simulating a sibling project that already ran)
        shared = EvidenceStore()
        shared.add(Finding(
            text="NextEra uses Mortenson in Texas projects",
            source_url="https://example.com/sibling-finding",
            source_tool="tavily_search",
            reliability="high",
            iteration=1,
        ))

        mock_plan.return_value = ["query1"]
        mock_sub_query.return_value = 1
        mock_reflect.return_value = ReflectionResult(
            summary="done", gaps=[], should_continue=False,
        )
        mock_synth.return_value = AgentResult(
            epc_contractor="Mortenson",
            confidence="likely",
            reasoning="Using shared finding",
            searches_performed=[],
        )

        result, log, tokens = await run_research(
            project=_sample_project(),
            knowledge_context=None,
            shared_findings=shared,
        )

        assert result.epc_contractor == "Mortenson"
        # Seed phase logged with correct count
        seed_entry = next((e for e in log if e.get("phase") == "seed"), None)
        assert seed_entry is not None
        assert seed_entry["shared_findings_count"] == 1


class TestSharedFindingsPropagation:
    """Verify that findings from a project flow back to the shared store."""

    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_local_findings_pushed_to_shared(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth
    ):
        """After research completes, findings added during fan-out propagate to shared."""
        from src.evidence import Finding as F
        from src.research import run_research

        shared = EvidenceStore()

        # Simulate execute_sub_query adding a finding to the local evidence store
        async def sub_query_side_effect(query, evidence, compressor, iteration=0):
            evidence.add(F(
                text="McCarthy Building Companies selected as EPC for Texas solar project",
                source_url="https://example.com/pr-discovered",
                source_tool="tavily_search",
                reliability="high",
                iteration=iteration,
            ))
            return 1

        mock_plan.return_value = ["NextEra Lone Star EPC"]
        mock_sub_query.side_effect = sub_query_side_effect
        mock_reflect.return_value = ReflectionResult(
            summary="done", gaps=[], should_continue=False,
        )
        mock_synth.return_value = AgentResult(
            epc_contractor="McCarthy",
            confidence="likely",
            reasoning="Found",
            searches_performed=["NextEra Lone Star EPC"],
        )

        assert len(shared.findings) == 0

        result, log, tokens = await run_research(
            project=_sample_project(),
            knowledge_context=None,
            shared_findings=shared,
        )

        # The finding extracted from the search result should now be in shared
        assert result.epc_contractor == "McCarthy"
        assert len(shared.findings) >= 1
        # Verify the specific URL propagated
        assert any(
            f.source_url == "https://example.com/pr-discovered"
            for f in shared.findings
        )


class TestBatchCreatesSharedStore:
    """Verify run_batch() wires up a shared EvidenceStore."""

    @patch("src.batch.store_discovery")
    @patch("src.batch.get_active_discovery", return_value=None)
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_all_projects_share_one_store(
        self, mock_kb, mock_run_research, mock_get_disco, mock_store
    ):
        """run_batch creates a single shared EvidenceStore and passes it to each project."""
        from src.batch import run_batch
        from src.models import AgentResult

        mock_run_research.return_value = (
            AgentResult(epc_contractor="McCarthy", confidence="likely"),
            [],
            100,
        )

        async def progress_noop(_: dict):
            pass

        projects = [_sample_project(f"p{i}") for i in range(3)]
        await run_batch(projects, progress_noop, concurrency=3)

        # All 3 calls should have received the same shared_findings instance
        assert mock_run_research.call_count == 3
        shared_instances = {
            id(call.kwargs.get("shared_findings"))
            for call in mock_run_research.call_args_list
        }
        # All three projects should share one instance
        assert len(shared_instances) == 1
        # And that instance should be an EvidenceStore, not None
        first_call = mock_run_research.call_args_list[0]
        assert isinstance(first_call.kwargs["shared_findings"], EvidenceStore)
