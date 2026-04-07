"""Tests for county-centroid geocoder."""

from src.geocoder import (
    geocode_county,
    geocode_project,
    geocode_projects,
    _normalize_county,
    _normalize_state,
)


class TestNormalization:
    def test_county_with_suffix(self):
        assert _normalize_county("Travis County") == "travis"

    def test_county_without_suffix(self):
        assert _normalize_county("Travis") == "travis"

    def test_parish(self):
        assert _normalize_county("Caddo Parish") == "caddo"

    def test_saint_abbreviation(self):
        assert _normalize_county("St. Louis County") == "saint louis"

    def test_extra_whitespace(self):
        assert _normalize_county("  San  Bernardino  County ") == "san bernardino"

    def test_state_abbreviation(self):
        assert _normalize_state("TX") == "TX"

    def test_state_full_name(self):
        assert _normalize_state("Texas") == "TX"

    def test_state_lowercase(self):
        assert _normalize_state("california") == "CA"


class TestGeocodeCounty:
    def test_texas_county(self):
        result = geocode_county("TX", "Travis")
        assert result is not None
        lat, lon = result
        assert 30.0 < lat < 31.0
        assert -98.0 < lon < -97.0

    def test_california_county(self):
        result = geocode_county("CA", "San Bernardino")
        assert result is not None
        lat, lon = result
        assert 34.0 < lat < 36.0
        assert -117.0 < lon < -115.0

    def test_with_county_suffix(self):
        result = geocode_county("TX", "Travis County")
        assert result is not None

    def test_full_state_name(self):
        result = geocode_county("Texas", "Travis")
        assert result is not None

    def test_missing_state(self):
        assert geocode_county(None, "Travis") is None

    def test_missing_county(self):
        assert geocode_county("TX", None) is None

    def test_unknown_county(self):
        assert geocode_county("TX", "Nonexistent") is None

    def test_multi_county(self):
        """Projects spanning multiple counties should match on the first."""
        result = geocode_county("WI", "Kenosha County,Racine County")
        assert result is not None

    def test_duplicate_forms(self):
        """ISO data sometimes has both short and long forms."""
        result = geocode_county("LA", "St. Mary,St. Mary Parish")
        assert result is not None

    def test_multi_county_indiana(self):
        result = geocode_county("IN", "Jasper County,Pulaski County")
        assert result is not None


class TestGeocodeProject:
    def test_adds_coordinates(self):
        project = {"state": "TX", "county": "Travis"}
        result = geocode_project(project)
        assert result["latitude"] is not None
        assert result["longitude"] is not None
        assert result["geocode_source"] == "county_centroid"

    def test_does_not_overwrite_existing(self):
        project = {
            "state": "TX",
            "county": "Travis",
            "latitude": 30.5,
            "longitude": -97.5,
            "geocode_source": "eia_860",
        }
        result = geocode_project(project)
        assert result["latitude"] == 30.5
        assert result["geocode_source"] == "eia_860"

    def test_no_match_leaves_none(self):
        project = {"state": "TX", "county": "Nonexistent"}
        result = geocode_project(project)
        assert result.get("latitude") is None


class TestGeocodeProjects:
    def test_batch(self):
        records = [
            {"state": "TX", "county": "Travis"},
            {"state": "CA", "county": "Kern"},
            {"state": "IL", "county": "McLean"},
        ]
        results = geocode_projects(records)
        assert all(r.get("latitude") is not None for r in results)
        assert all(r.get("geocode_source") == "county_centroid" for r in results)
