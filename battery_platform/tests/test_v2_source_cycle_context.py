"""Verified source cycles remain numeric and never become platform UTC time."""
import pytest

from app.agent import public_context


def query():
    return {"query_time": 21.0, "visible_cutoff": 20.0, "feature_max_time": 20.0,
            "reference_cutoff": 18.0, "available_at": 20.0, "source_id": "handmade-cycle-source",
            "time_basis": "verified_physical_cycle", "physical_cycles_known": True}


def test_explicit_verified_physical_cycles_are_separate_from_iso_cutoff():
    result = public_context({"query": query()}, cutoff="2026-09-01T00:00:00Z", installation_id="i")
    assert result["query"] == query() and isinstance(result["query"]["available_at"], float)
    for key in ("feature_max_time", "reference_cutoff", "available_at"):
        changed = query()
        changed[key] = 21.0
        assert "query" not in public_context({"query": changed}, cutoff="2026-09-01T00:00:00Z", installation_id="i")


@pytest.mark.parametrize("flag", [None, False, 1, "true"])
def test_cycle_basis_without_exact_verified_flag_is_rejected(flag):
    changed = query()
    changed["physical_cycles_known"] = flag
    with pytest.raises(ValueError, match="cycle evidence flag"):
        public_context({"query": changed}, cutoff="2026-09-01T00:00:00Z", installation_id="i")
