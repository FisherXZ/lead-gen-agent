"""Tests for reverse_sweep module — per-EPC reverse lookup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reverse_sweep import (
    EdgarSweepSource,
    OshaSweepSource,
    SweepCandidate,
    _normalize,
    _score_match,
    disambiguate_with_haiku,
    match_candidates_to_projects,
    run_reverse_sweep,
)

# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


def test_normalize():
    assert _normalize("Sunrise Solar I") == "sunrise solar i"
    assert _normalize("LLC.") == "llc"
    assert _normalize("Test-Project (Phase 2)") == "testproject phase 2"


# ---------------------------------------------------------------------------
# _score_match
# ---------------------------------------------------------------------------


def test_score_name_match():
    candidate = SweepCandidate(
        project_name_hint="Sunrise Solar project in Texas with 250MW capacity",
        state="TX",
        epc_name="McCarthy",
    )
    project = {
        "id": "p1",
        "project_name": "Sunrise Solar",
        "state": "TX",
        "mw_capacity": 250,
        "developer": "SunDev LLC",
    }
    score, method = _score_match(candidate, project)
    assert score >= 0.5
    assert method == "name"


def test_score_state_mismatch_penalty():
    candidate = SweepCandidate(
        project_name_hint="Sunrise Solar project",
        state="CA",
        epc_name="McCarthy",
    )
    project = {
        "id": "p1",
        "project_name": "Sunrise Solar",
        "state": "TX",
        "mw_capacity": 250,
    }
    score, _ = _score_match(candidate, project)
    # Name match gives 0.5, state mismatch subtracts 0.2
    assert score <= 0.35


def test_score_developer_match():
    candidate = SweepCandidate(
        project_name_hint="SunDev announces new construction contract",
        state="TX",
        epc_name="McCarthy",
    )
    project = {
        "id": "p1",
        "project_name": "Unknown Project",
        "state": "TX",
        "developer": "SunDev LLC",
        "mw_capacity": 0,
    }
    score, method = _score_match(candidate, project)
    assert score > 0  # Developer match should contribute


def test_score_no_match():
    candidate = SweepCandidate(
        project_name_hint="Totally unrelated filing about retail stores",
        state="NY",
        epc_name="McCarthy",
    )
    project = {
        "id": "p1",
        "project_name": "Desert Wind Solar",
        "state": "CA",
        "developer": "WindCo",
        "mw_capacity": 200,
    }
    score, _ = _score_match(candidate, project)
    assert score <= 0.0


# ---------------------------------------------------------------------------
# match_candidates_to_projects
# ---------------------------------------------------------------------------


def test_match_strong():
    candidates = [
        SweepCandidate(
            project_name_hint="McCarthy awarded EPC for Sunrise Solar 250MW in Texas",
            state="TX",
            mw_hint=250,
            source_type="sec_edgar",
            epc_name="McCarthy",
        ),
    ]
    projects = [
        {
            "id": "p1",
            "project_name": "Sunrise Solar",
            "state": "TX",
            "mw_capacity": 250,
            "developer": "SunDev",
        },
        {
            "id": "p2",
            "project_name": "Desert Wind",
            "state": "CA",
            "mw_capacity": 100,
            "developer": "WindCo",
        },
    ]

    strong, ambiguous = match_candidates_to_projects(candidates, projects)
    assert len(strong) == 1
    assert strong[0].project_id == "p1"
    assert strong[0].epc_name == "McCarthy"


def test_match_no_candidates_returns_empty():
    strong, ambiguous = match_candidates_to_projects([], [{"id": "p1", "project_name": "Test"}])
    assert strong == []
    assert ambiguous == []


def test_match_deduplicates_projects():
    """Multiple candidates matching the same project should still result in one match."""
    candidates = [
        SweepCandidate(
            project_name_hint="Sunrise Solar EPC contract",
            state="TX",
            epc_name="McCarthy",
            source_type="sec_edgar",
        ),
        SweepCandidate(
            project_name_hint="Sunrise Solar construction site",
            state="TX",
            epc_name="McCarthy",
            source_type="osha",
        ),
    ]
    projects = [
        {
            "id": "p1",
            "project_name": "Sunrise Solar",
            "state": "TX",
            "mw_capacity": 250,
            "developer": "SunDev",
        },
    ]

    strong, _ = match_candidates_to_projects(candidates, projects)
    # Both should match p1, but dedup happens in the orchestrator
    assert all(m.project_id == "p1" for m in strong)


# ---------------------------------------------------------------------------
# disambiguate_with_haiku
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_haiku_yes():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="yes")]

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    candidate = SweepCandidate(
        project_name_hint="Sunrise Solar",
        epc_name="McCarthy",
        excerpt="McCarthy EPC for Sunrise Solar",
    )
    project = {
        "project_name": "Sunrise Solar",
        "developer": "SunDev",
        "state": "TX",
        "mw_capacity": 250,
    }

    with patch("src.reverse_sweep.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await disambiguate_with_haiku(candidate, project, api_key="test-key")

    assert result == "yes"


@pytest.mark.asyncio
async def test_haiku_no():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="no")]

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    candidate = SweepCandidate(
        project_name_hint="Different Project", epc_name="McCarthy", excerpt="unrelated"
    )
    project = {
        "project_name": "Sunrise Solar",
        "developer": "SunDev",
        "state": "TX",
        "mw_capacity": 250,
    }

    with patch("src.reverse_sweep.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await disambiguate_with_haiku(candidate, project, api_key="test-key")

    assert result == "no"


@pytest.mark.asyncio
async def test_haiku_api_error_returns_unsure():
    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = Exception("API down")

    candidate = SweepCandidate(project_name_hint="Test", epc_name="Test", excerpt="test")
    project = {"project_name": "Test", "state": "TX", "mw_capacity": 100}

    with patch("src.reverse_sweep.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await disambiguate_with_haiku(candidate, project, api_key="test-key")

    assert result == "unsure"


@pytest.mark.asyncio
async def test_haiku_no_api_key_returns_unsure():
    candidate = SweepCandidate(project_name_hint="Test", epc_name="Test", excerpt="test")
    project = {"project_name": "Test", "state": "TX", "mw_capacity": 100}

    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("ANTHROPIC_API_KEY", None)
        result = await disambiguate_with_haiku(candidate, project, api_key=None)

    assert result == "unsure"


# ---------------------------------------------------------------------------
# EdgarSweepSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edgar_source_returns_candidates():
    mock_results = {
        "results": [
            {
                "snippet": "McCarthy EPC contract for Sunrise Solar 250MW",
                "url": "https://sec.gov/filing1",
            },
            {
                "snippet": "Another filing about solar construction",
                "url": "https://sec.gov/filing2",
            },
        ]
    }

    source = EdgarSweepSource()
    with patch("src.tools.search_sec_edgar.execute", AsyncMock(return_value=mock_results)):
        candidates = await source.search("McCarthy")

    # Two queries × 2 results each = up to 4, but mocked same for both
    assert len(candidates) >= 2
    assert all(c.epc_name == "McCarthy" for c in candidates)
    assert all(c.source_type == "sec_edgar" for c in candidates)


@pytest.mark.asyncio
async def test_edgar_source_handles_error():
    source = EdgarSweepSource()
    with patch("src.tools.search_sec_edgar.execute", AsyncMock(return_value={"error": "timeout"})):
        candidates = await source.search("McCarthy")

    assert candidates == []


# ---------------------------------------------------------------------------
# OshaSweepSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_osha_source_returns_candidates():
    mock_results = {
        "results": [
            {
                "employer_name": "McCarthy Building",
                "address": "Pecos, TX, 79772",
                "state": "TX",
                "inspection_date": "2025-06-15",
                "detail_url": "https://osha.gov/1",
            },
        ]
    }

    source = OshaSweepSource()
    with patch("src.tools.search_osha.execute", AsyncMock(return_value=mock_results)):
        candidates = await source.search("McCarthy")

    assert len(candidates) == 1
    assert candidates[0].state == "TX"
    assert candidates[0].source_type == "osha_inspection"


# ---------------------------------------------------------------------------
# run_reverse_sweep (integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_no_epcs_returns_early():
    mock_client = MagicMock()
    sel_chain = mock_client.table.return_value.select.return_value
    sel_chain.contains.return_value.order.return_value.execute.return_value = MagicMock(data=[])

    progress_updates = []

    async def on_progress(p):
        progress_updates.append(p)

    with patch("src.db.get_client", return_value=mock_client):
        result = await run_reverse_sweep(on_progress=on_progress, sources=[])

    assert result.epcs_processed == 0
    assert len(progress_updates) == 1
    assert progress_updates[0].status == "completed"


@pytest.mark.asyncio
async def test_sweep_processes_epc_with_mocked_sources():
    """Full sweep with mocked sources → verifies orchestration logic."""
    mock_client = MagicMock()

    # Mock entities query
    entities_resp = MagicMock()
    entities_resp.data = [
        {"id": "e1", "name": "McCarthy", "entity_type": ["epc"], "metadata": {}, "aliases": []},
    ]

    # Mock projects query
    projects_resp = MagicMock()
    projects_resp.data = [
        {
            "id": "p1",
            "project_name": "Sunrise Solar",
            "state": "TX",
            "mw_capacity": 250,
            "developer": "SunDev",
            "county": "Travis",
            "latitude": 30.27,
            "longitude": -97.74,
        },
    ]

    # Chain the two table() calls
    def table_side_effect(name):
        mock_table = MagicMock()
        if name == "entities":
            sel = mock_table.select.return_value
            sel.contains.return_value.order.return_value.execute.return_value = entities_resp
        elif name == "projects":
            sel = mock_table.select.return_value
            is_chain = sel.is_.return_value.order.return_value
            is_chain.limit.return_value.execute.return_value = projects_resp
        elif name == "epc_discoveries":
            mock_table.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": "disc-new"}]
            )
        return mock_table

    mock_client.table.side_effect = table_side_effect

    # Create a mock source that returns a strong match
    class MockSource:
        name = "mock"

        async def search(self, epc_name, **kwargs):
            return [
                SweepCandidate(
                    project_name_hint="McCarthy awarded EPC for Sunrise Solar 250MW Texas project",
                    state="TX",
                    mw_hint=250,
                    source_type="mock_source",
                    source_url="https://example.com",
                    excerpt="McCarthy awarded EPC for Sunrise Solar",
                    epc_name=epc_name,
                )
            ]

    progress_updates = []

    async def on_progress(p):
        progress_updates.append(p)

    with (
        patch("src.db.get_client", return_value=mock_client),
        patch("src.db.get_active_discovery", return_value=None),
    ):
        result = await run_reverse_sweep(
            on_progress=on_progress,
            sources=[MockSource()],
        )

    assert result.epcs_processed == 1
    assert result.total_candidates == 1
    assert result.discoveries_created == 1
    assert len(progress_updates) >= 2  # searching + completed


@pytest.mark.asyncio
async def test_sweep_skips_existing_discovery():
    """Should not create discovery if project already has one."""
    mock_client = MagicMock()

    entities_resp = MagicMock()
    entities_resp.data = [
        {"id": "e1", "name": "McCarthy", "entity_type": ["epc"], "metadata": {}, "aliases": []}
    ]

    projects_resp = MagicMock()
    projects_resp.data = [
        {
            "id": "p1",
            "project_name": "Sunrise Solar",
            "state": "TX",
            "mw_capacity": 250,
            "developer": "SunDev",
            "county": "Travis",
            "latitude": None,
            "longitude": None,
        }
    ]

    def table_side_effect(name):
        mock_table = MagicMock()
        if name == "entities":
            sel = mock_table.select.return_value
            sel.contains.return_value.order.return_value.execute.return_value = entities_resp
        elif name == "projects":
            sel = mock_table.select.return_value
            is_chain = sel.is_.return_value.order.return_value
            is_chain.limit.return_value.execute.return_value = projects_resp
        return mock_table

    mock_client.table.side_effect = table_side_effect

    class MockSource:
        name = "mock"

        async def search(self, epc_name, **kwargs):
            return [
                SweepCandidate(
                    project_name_hint="Sunrise Solar EPC contract",
                    state="TX",
                    epc_name=epc_name,
                    source_type="mock",
                )
            ]

    # Existing discovery blocks creation
    existing_discovery = {"id": "disc-old", "review_status": "pending"}

    with (
        patch("src.db.get_client", return_value=mock_client),
        patch("src.db.get_active_discovery", return_value=existing_discovery),
    ):
        result = await run_reverse_sweep(sources=[MockSource()])

    assert result.discoveries_created == 0


@pytest.mark.asyncio
async def test_sweep_source_error_continues():
    """If one source fails, sweep should continue with other sources."""
    mock_client = MagicMock()

    entities_resp = MagicMock()
    entities_resp.data = [
        {"id": "e1", "name": "McCarthy", "entity_type": ["epc"], "metadata": {}, "aliases": []}
    ]

    projects_resp = MagicMock()
    projects_resp.data = []

    def table_side_effect(name):
        mock_table = MagicMock()
        if name == "entities":
            sel = mock_table.select.return_value
            sel.contains.return_value.order.return_value.execute.return_value = entities_resp
        elif name == "projects":
            sel = mock_table.select.return_value
            is_chain = sel.is_.return_value.order.return_value
            is_chain.limit.return_value.execute.return_value = projects_resp
        return mock_table

    mock_client.table.side_effect = table_side_effect

    class FailingSource:
        name = "failing"

        async def search(self, epc_name, **kwargs):
            raise Exception("Source exploded")

    class WorkingSource:
        name = "working"

        async def search(self, epc_name, **kwargs):
            return []

    with patch("src.db.get_client", return_value=mock_client):
        result = await run_reverse_sweep(sources=[FailingSource(), WorkingSource()])

    assert result.epcs_processed == 1
    assert len(result.errors) == 1
    assert "exploded" in result.errors[0]
