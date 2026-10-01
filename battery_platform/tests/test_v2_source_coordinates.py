"""Verified cycle coordinates retain their meaning at the Agent boundary."""
import pytest

from app.api_v2 import source_time_view
from app.agent.contracts import public_context


def test_verified_physical_cycles_reach_context_without_wall_clock_conversion():
    query = {"source_id": "matr", "time_basis": "verified_physical_cycle", "physical_cycles_known": True,
             "query_time": 100, "visible_cutoff": 99, "feature_max_time": 99, "reference_cutoff": 10}
    result = source_time_view(query)
    assert result["source_time"] == {"time_basis": "verified_physical_cycle", "unit": "physical_cycle",
                                     "source_id": "matr", "physical_cycles_known": True,
                                     "query_cycle": 100, "visible_cutoff_cycle": 99,
                                     "feature_max_cycle": 99, "reference_cutoff_cycle": 10}
    assert result["time_basis"] == "verified_physical_cycle"
    assert result["query_time"] == 100 and query.get("source_time") is None
    assert public_context(result, cutoff="2026-10-02T00:00:00Z", installation_id="i") == result


@pytest.mark.parametrize("declared", [False, None, 1, "true"])
def test_numeric_source_records_need_strict_physical_cycle_proof(declared):
    result = source_time_view({"source_id": "matr", "time_basis": "verified_physical_cycle",
                               "physical_cycles_known": declared, "query_time": 100, "visible_cutoff": 99})
    assert result["time_basis"] == "source_record_ordinal"
    assert result["source_time"]["query_ordinal"] == 100
    assert "unit" not in result["source_time"]
    sanitized = public_context(result, cutoff="2026-10-02T00:00:00Z", installation_id="i")
    assert sanitized["time_basis"] == "source_record_ordinal"
    assert sanitized["source_time"] == result["source_time"]
    assert sanitized["query_time"] == 100


def test_wall_clock_query_is_not_relabelled_as_numeric_source_coordinate():
    query = {"source_id": "source", "query_time": "2026-10-01T00:00:00Z", "visible_cutoff": "2026-10-01T00:00:00Z"}
    assert source_time_view(query) == query
