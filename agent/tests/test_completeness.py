"""Tests for completeness evaluation (Harvey AI pattern)."""

from src.completeness import (
    CHECKPOINTS,
    _has_new_signals,
    _is_epc_domain,
    _is_portfolio_check,
    evaluate_completeness,
)

# ---------------------------------------------------------------------------
# Checkpoint configuration
# ---------------------------------------------------------------------------


class TestCheckpoints:
    def test_checkpoint_iterations(self):
        assert set(CHECKPOINTS.keys()) == {6, 12, 18}

    def test_escalation_levels(self):
        assert CHECKPOINTS[6] == "gentle"
        assert CHECKPOINTS[12] == "firm"
        assert CHECKPOINTS[18] == "mandatory"


# ---------------------------------------------------------------------------
# Portfolio check detection
# ---------------------------------------------------------------------------


class TestPortfolioCheck:
    def test_site_query_detected(self):
        assert _is_portfolio_check('site:mccarthybuilding.com "NextEra"') is True

    def test_site_query_mortenson(self):
        assert _is_portfolio_check("site:mortenson.com solar EPC Texas") is True

    def test_non_site_query(self):
        assert _is_portfolio_check("NextEra solar EPC Texas") is False

    def test_unknown_site(self):
        assert _is_portfolio_check("site:randomsite.com solar") is False

    def test_case_insensitive(self):
        assert _is_portfolio_check('SITE:McCarthyBuilding.com "test"') is True


# ---------------------------------------------------------------------------
# EPC domain detection
# ---------------------------------------------------------------------------


class TestEpcDomain:
    def test_known_domain(self):
        assert _is_epc_domain("https://www.mccarthybuilding.com/projects/solar") is True

    def test_unknown_domain(self):
        assert _is_epc_domain("https://www.example.com/page") is False

    def test_solv_energy(self):
        assert _is_epc_domain("https://solvenergyus.com/portfolio") is True


# ---------------------------------------------------------------------------
# New signals detection
# ---------------------------------------------------------------------------


class TestNewSignals:
    def test_epc_mention_detected(self):
        outputs = [
            {"results": [{"title": "McCarthy awarded 200MW solar EPC contract"}]},
        ]
        assert _has_new_signals(outputs) is True

    def test_error_results_ignored(self):
        outputs = [
            {"error": "rate limit exceeded"},
            {"error": "timeout"},
        ]
        assert _has_new_signals(outputs) is False

    def test_empty_results_no_signal(self):
        outputs = [{"results": []}]
        assert _has_new_signals(outputs) is False

    def test_short_content_no_signal(self):
        outputs = [{"ok": True}]
        assert _has_new_signals(outputs) is False

    def test_non_epc_content(self):
        outputs = [
            {
                "results": [
                    {
                        "title": "Solar panel efficiency improvements in 2026",
                        "url": "https://example.com",
                        "content": (
                            "New solar panel technology achieves 25% efficiency "
                            "gains in laboratory testing according to researchers"
                        ),
                    }
                ]
            },
        ]
        assert _has_new_signals(outputs) is False


# ---------------------------------------------------------------------------
# Full evaluation — iteration 6 (gentle)
# ---------------------------------------------------------------------------


class TestGentleCheckpoint:
    def test_no_gaps_with_signals_returns_continue(self):
        """Research on track — no message needed."""
        agent_log = [
            {"tool": "query_knowledge_base", "input": {"entity_name": "NextEra"}},
            {"tool": "web_search", "input": {"query": "NextEra solar EPC"}},
            {"tool": "web_search", "input": {"query": 'site:mccarthybuilding.com "NextEra"'}},
            {"tool": "web_search", "input": {"query": 'site:mortenson.com "NextEra"'}},
            {
                "tool": "fetch_page",
                "input": {"url": "https://mccarthybuilding.com/projects/nextera"},
            },
        ]
        recent = [
            {"results": [{"title": "McCarthy Building solar EPC contractor for NextEra project"}]},
        ]
        result = evaluate_completeness(6, agent_log, recent)
        assert result["recommendation"] == "continue"
        assert result["message"] is None
        assert result["kb_consulted"] is True
        assert result["portfolio_checks"] >= 2

    def test_missing_portfolio_checks(self):
        """Phase 2 not started — should flag it."""
        agent_log = [
            {"tool": "web_search", "input": {"query": "NextEra solar EPC Texas"}},
            {"tool": "web_search", "input": {"query": "NextEra solar construction"}},
            {"tool": "web_search", "input": {"query": "NextEra groundbreaking solar"}},
            {"tool": "fetch_page", "input": {"url": "https://example.com/article"}},
        ]
        recent = [{"results": [{"title": "No EPC info found"}]}]
        result = evaluate_completeness(6, agent_log, recent)
        assert result["recommendation"] == "switch_strategy"
        assert result["message"] is not None
        assert "portfolio" in result["message"].lower()
        assert result["portfolio_checks"] == 0

    def test_missing_kb(self):
        """KB not consulted — should flag it."""
        agent_log = [
            {"tool": "web_search", "input": {"query": 'site:mccarthybuilding.com "Dev"'}},
            {"tool": "web_search", "input": {"query": 'site:mortenson.com "Dev"'}},
            {"tool": "web_search", "input": {"query": 'site:blattnerenergy.com "Dev"'}},
        ]
        recent = [{"results": []}]
        result = evaluate_completeness(6, agent_log, recent)
        assert result["kb_consulted"] is False
        assert "knowledge base" in result["message"].lower()


# ---------------------------------------------------------------------------
# Full evaluation — iteration 12 (firm)
# ---------------------------------------------------------------------------


class TestFirmCheckpoint:
    def test_no_new_signals_wrap_up(self):
        """Diminishing returns — should firmly suggest wrap up."""
        agent_log = [{"tool": "web_search", "input": {"query": f"search {i}"}} for i in range(10)]
        recent = [{"error": "no results"}, {"results": []}]
        result = evaluate_completeness(12, agent_log, recent)
        assert result["recommendation"] == "wrap_up"
        assert result["level"] == "firm"
        assert "SHOULD" in result["message"]

    def test_still_finding_signals_continue(self):
        """New signals at iteration 12 — let it continue with a nudge."""
        agent_log = [{"tool": "web_search", "input": {"query": f"search {i}"}} for i in range(10)]
        recent = [
            {"results": [{"title": "Blattner selected as EPC contractor for 300MW solar"}]},
        ]
        result = evaluate_completeness(12, agent_log, recent)
        assert result["recommendation"] == "continue"
        assert result["message"] is not None  # Still gets a nudge
        assert "SHOULD" in result["message"]


# ---------------------------------------------------------------------------
# Full evaluation — iteration 18 (mandatory)
# ---------------------------------------------------------------------------


class TestMandatoryCheckpoint:
    def test_mandatory_always_wraps_up(self):
        """Iteration 18 — must wrap up regardless of signals."""
        agent_log = [{"tool": "web_search", "input": {"query": f"search {i}"}} for i in range(15)]
        recent = [
            {"results": [{"title": "EPC contractor awarded huge solar project"}]},
        ]
        result = evaluate_completeness(18, agent_log, recent)
        assert result["recommendation"] == "wrap_up"
        assert result["level"] == "mandatory"
        assert "MUST" in result["message"]


# ---------------------------------------------------------------------------
# Metrics accuracy
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_search_count(self):
        agent_log = [
            {"tool": "web_search", "input": {"query": "q1"}},
            {"tool": "web_search_broad", "input": {"query": "q2"}},
            {"tool": "fetch_page", "input": {"url": "https://example.com"}},
            {"tool": "notify_progress", "input": {"status": "searching"}},
        ]
        result = evaluate_completeness(6, agent_log, [])
        assert result["search_count"] == 2
        assert result["fetch_count"] == 1

    def test_error_rate(self):
        recent = [
            {"results": "ok"},
            {"error": "fail"},
            {"error": "fail"},
        ]
        result = evaluate_completeness(6, [], recent)
        assert abs(result["error_rate"] - 0.67) < 0.01

    def test_fetch_epc_domain_counts_as_portfolio(self):
        agent_log = [
            {"tool": "fetch_page", "input": {"url": "https://www.mortenson.com/solar-projects"}},
        ]
        result = evaluate_completeness(6, agent_log, [])
        assert result["portfolio_checks"] == 1
