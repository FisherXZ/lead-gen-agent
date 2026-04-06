"""Tests for search_linkedin tool module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Pydantic Input validation
# ---------------------------------------------------------------------------


def test_input_defaults():
    from src.tools.search_linkedin import Input

    inp = Input(company_name="Signal Energy")
    assert inp.company_name == "Signal Energy"
    assert "project manager" in inp.role_keywords
    assert inp.location is None
    assert inp.max_results == 5


def test_input_max_results_bounds():
    from pydantic import ValidationError

    from src.tools.search_linkedin import Input

    with pytest.raises(ValidationError):
        Input(company_name="Acme", max_results=0)

    with pytest.raises(ValidationError):
        Input(company_name="Acme", max_results=21)

    # Boundary values should be valid
    inp_min = Input(company_name="Acme", max_results=1)
    inp_max = Input(company_name="Acme", max_results=20)
    assert inp_min.max_results == 1
    assert inp_max.max_results == 20


def test_input_company_name_required():
    from pydantic import ValidationError

    from src.tools.search_linkedin import Input

    with pytest.raises(ValidationError):
        Input()


def test_input_with_location():
    from src.tools.search_linkedin import Input

    inp = Input(company_name="Blattner Energy", location="Texas", max_results=3)
    assert inp.location == "Texas"
    assert inp.max_results == 3


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def test_build_search_queries_basic():
    """Constructs correct site:linkedin.com/in queries for each role keyword."""
    from src.tools.search_linkedin import _build_search_queries

    queries = _build_search_queries(
        company_name="Signal Energy",
        role_keywords=["project manager", "VP construction"],
        location=None,
    )

    assert len(queries) == 2
    assert "site:linkedin.com/in" in queries[0]
    assert '"Signal Energy"' in queries[0]
    assert '"project manager"' in queries[0]
    assert '"VP construction"' in queries[1]


def test_build_search_queries_with_location():
    """Location is appended to the query when provided."""
    from src.tools.search_linkedin import _build_search_queries

    queries = _build_search_queries(
        company_name="Blattner Energy",
        role_keywords=["director operations"],
        location="Texas",
    )

    assert "Texas" in queries[0]


def test_build_search_queries_no_location():
    """Without location, query does not contain stray location text."""
    from src.tools.search_linkedin import _build_search_queries

    queries = _build_search_queries(
        company_name="Acme Solar",
        role_keywords=["VP construction"],
        location=None,
    )

    assert "None" not in queries[0]


# ---------------------------------------------------------------------------
# LinkedIn URL extraction
# ---------------------------------------------------------------------------


def test_extract_linkedin_urls_from_results():
    """Parses linkedin.com/in URLs and name/title snippets from search results."""
    from src.tools.search_linkedin import _extract_candidates

    search_results = [
        {
            "url": "https://www.linkedin.com/in/tomrivera",
            "title": "Tom Rivera - Senior Project Manager at Signal Energy | LinkedIn",
            "content": "Tom Rivera. Senior Project Manager at Signal Energy. Houston, TX.",
        },
        {
            "url": "https://example.com/not-linkedin",
            "title": "Some other site",
            "content": "Not relevant",
        },
        {
            "url": "https://linkedin.com/in/janedoe",
            "title": "Jane Doe – VP Construction | LinkedIn",
            "content": "Jane Doe. VP Construction. Dallas, TX.",
        },
    ]

    candidates = _extract_candidates(search_results)

    assert len(candidates) == 2
    assert candidates[0]["linkedin_url"] == "https://www.linkedin.com/in/tomrivera"
    assert candidates[1]["linkedin_url"] == "https://linkedin.com/in/janedoe"


def test_extract_candidates_deduplicates_urls():
    """Same LinkedIn URL appearing in multiple results is deduped."""
    from src.tools.search_linkedin import _extract_candidates

    results = [
        {"url": "https://linkedin.com/in/tomrivera", "title": "Tom Rivera", "content": ""},
        {
            "url": "https://linkedin.com/in/tomrivera",
            "title": "Tom Rivera duplicate",
            "content": "",
        },
    ]

    candidates = _extract_candidates(results)
    assert len(candidates) == 1


def test_extract_candidates_empty_results():
    from src.tools.search_linkedin import _extract_candidates

    assert _extract_candidates([]) == []


# ---------------------------------------------------------------------------
# Graceful degradation without APIFY_API_TOKEN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_apify_token_returns_search_only():
    """When APIFY_API_TOKEN is not set, return search results without enrichment."""
    from src.tools.search_linkedin import execute

    mock_search_result = {
        "results": [
            {
                "url": "https://linkedin.com/in/tomrivera",
                "title": "Tom Rivera - Senior PM at Signal Energy | LinkedIn",
                "content": "Senior Project Manager at Signal Energy. Houston, TX.",
                "score": 0.9,
            }
        ]
    }

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("APIFY_API_TOKEN", None)
        with patch("src.tools.search_linkedin._run_web_search", return_value=mock_search_result):
            result = await execute(
                {
                    "company_name": "Signal Energy",
                    "role_keywords": ["project manager"],
                    "max_results": 5,
                }
            )

    assert result["status"] == "success"
    assert result["data"]["enriched"] is False
    assert len(result["data"]["candidates"]) >= 1
    assert result["data"]["candidates"][0]["linkedin_url"] == "https://linkedin.com/in/tomrivera"
    assert result["source"] == "linkedin"


@pytest.mark.asyncio
async def test_no_apify_token_no_crash():
    """Execute completes without raising even if Apify token is missing."""
    from src.tools.search_linkedin import execute

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("APIFY_API_TOKEN", None)
        with patch("src.tools.search_linkedin._run_web_search", return_value={"results": []}):
            result = await execute({"company_name": "Acme Solar"})

    assert "status" in result
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Full enrichment path (Apify available)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"APIFY_API_TOKEN": "test-apify-token"})
async def test_apify_enrichment_called_with_linkedin_urls():
    """When APIFY_API_TOKEN is set, Apify is called with the extracted URLs."""
    from src.tools.search_linkedin import execute

    mock_search_result = {
        "results": [
            {
                "url": "https://linkedin.com/in/tomrivera",
                "title": "Tom Rivera - Senior PM at Signal Energy | LinkedIn",
                "content": "Senior PM at Signal Energy.",
                "score": 0.9,
            }
        ]
    }

    apify_profile = {
        "fullName": "Tom Rivera",
        "headline": "Senior PM | Solar & Renewable Energy",
        "jobTitle": "Senior Project Manager",
        "addressWithCountry": "Houston, TX",
        "url": "https://linkedin.com/in/tomrivera",
        "positions": {
            "positionHistory": [
                {
                    "companyName": "Signal Energy",
                    "title": "Senior PM",
                    "startEndDate": {"start": {"year": 2023}},
                }
            ]
        },
    }

    with (
        patch("src.tools.search_linkedin.cache_get", return_value=None),
        patch("src.tools.search_linkedin.cache_set"),
        patch("src.tools.search_linkedin._run_web_search", return_value=mock_search_result),
        patch("src.tools.search_linkedin._enrich_with_apify", return_value=[apify_profile]),
    ):
        result = await execute(
            {
                "company_name": "Signal Energy",
                "role_keywords": ["project manager"],
                "max_results": 5,
            }
        )

    assert result["status"] == "success"
    assert result["data"]["enriched"] is True
    candidates = result["data"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["full_name"] == "Tom Rivera"
    assert candidates[0]["linkedin_url"] == "https://linkedin.com/in/tomrivera"
    assert candidates[0]["source"] == "linkedin"


@pytest.mark.asyncio
@patch.dict(os.environ, {"APIFY_API_TOKEN": "test-apify-token"})
async def test_apify_failure_falls_back_to_search_results():
    """If Apify call fails, fall back to search-only results without crashing."""
    from src.tools.search_linkedin import execute

    mock_search_result = {
        "results": [
            {
                "url": "https://linkedin.com/in/janesmith",
                "title": "Jane Smith - VP Construction | LinkedIn",
                "content": "VP of Construction at Blattner.",
                "score": 0.85,
            }
        ]
    }

    with (
        patch("src.tools.search_linkedin.cache_get", return_value=None),
        patch("src.tools.search_linkedin.cache_set"),
        patch("src.tools.search_linkedin._run_web_search", return_value=mock_search_result),
        patch(
            "src.tools.search_linkedin._enrich_with_apify", side_effect=Exception("Apify timeout")
        ),
    ):
        result = await execute(
            {
                "company_name": "Blattner Energy",
                "role_keywords": ["VP construction"],
                "max_results": 5,
            }
        )

    assert result["status"] == "success"
    assert result["data"]["enriched"] is False
    assert len(result["data"]["candidates"]) == 1


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_skips_search():
    """A cache hit returns immediately without calling web search."""
    from src.tools.search_linkedin import execute

    cached_data = {
        "candidates": [
            {"full_name": "Cached Person", "linkedin_url": "https://linkedin.com/in/cached"}
        ],
        "enriched": False,
    }

    with (
        patch("src.tools.search_linkedin.cache_get", return_value=cached_data),
        patch("src.tools.search_linkedin._run_web_search") as mock_search,
    ):
        result = await execute({"company_name": "Signal Energy"})

    mock_search.assert_not_called()
    assert result["status"] == "success"
    assert result["data"] == cached_data
    assert result.get("cached") is True


# ---------------------------------------------------------------------------
# max_results respected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_results_limits_candidates():
    """Only up to max_results candidates are returned."""
    from src.tools.search_linkedin import execute

    # Return 10 distinct LinkedIn URLs from search
    results = [
        {
            "url": f"https://linkedin.com/in/person{i}",
            "title": f"Person {i} | LinkedIn",
            "content": f"Person {i} at Acme.",
            "score": 0.8,
        }
        for i in range(10)
    ]

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("APIFY_API_TOKEN", None)
        with patch("src.tools.search_linkedin._run_web_search", return_value={"results": results}):
            result = await execute(
                {
                    "company_name": "Acme Solar",
                    "role_keywords": ["project manager"],
                    "max_results": 3,
                }
            )

    assert len(result["data"]["candidates"]) <= 3


# ---------------------------------------------------------------------------
# DEFINITION dict
# ---------------------------------------------------------------------------


def test_definition_name():
    from src.tools.search_linkedin import DEFINITION

    assert DEFINITION["name"] == "search_linkedin"


def test_definition_has_description():
    from src.tools.search_linkedin import DEFINITION

    desc = DEFINITION["description"].lower()
    assert "linkedin" in desc
    assert "company" in desc or "people" in desc or "contact" in desc


def test_definition_input_schema():
    from src.tools.search_linkedin import DEFINITION

    schema = DEFINITION["input_schema"]
    assert "company_name" in schema["properties"]
    assert "company_name" in schema["required"]
