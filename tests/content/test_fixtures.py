"""Independent analytical and runtime regression checks for evaluator fixtures."""

import copy
import json
import math

import pytest

from tools.content.fixtures import (
    CARBON_REQUIRED_TOPICS,
    DISPATCH_REQUIRED_TOPICS,
    budget_support,
    carbon_fixtures,
    compare_expected,
    dispatch_fixtures,
    dispatch_runtime_adapter,
    evaluate_carbon,
    generate_fixtures,
    renewal_counts,
    validate_dispatch_solution,
    validate_fixture,
    validate_fixtures,
)


DISPATCH = dispatch_fixtures()
CARBON = carbon_fixtures()
BY_ID = {row["fixture_id"]: row for row in [*DISPATCH, *CARBON]}


def test_fixture_counts_provenance_coverage_and_determinism(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    stats = generate_fixtures(first)
    assert stats["dispatch_count"] == 40
    assert stats["carbon_count"] == 30
    assert DISPATCH_REQUIRED_TOPICS <= set(stats["coverage"]["dispatch"])
    assert CARBON_REQUIRED_TOPICS <= set(stats["coverage"]["carbon"])
    generate_fixtures(second)
    for name in ("dispatch", "carbon"):
        assert (first / "fixtures" / f"{name}.jsonl").read_bytes() == (second / "fixtures" / f"{name}.jsonl").read_bytes()
    report = validate_fixtures(first)
    assert report["valid"], report["errors"]
    assert all(row["synthetic"] and row["data_scope"] == "demo_synthetic" for row in [*DISPATCH, *CARBON])


@pytest.mark.parametrize("fixture", DISPATCH, ids=lambda fixture: fixture["fixture_id"])
def test_cpsat_matches_independent_exhaustive_oracle(fixture):
    # This imports the product solver only here. The golden oracle never imports
    # CP-SAT, so a changed optimizer is checked against separate enumeration.
    from app.dispatch.solver import OBJECTIVE_NAMES, solve, validate_assignments

    adapter = dispatch_runtime_adapter(fixture["inputs"])
    result = solve(adapter["data"], time_limit_seconds=5)
    assert result["status"] == "optimal", result
    assert result["lexicographic_complete"]
    assert [result["objectives"][name] for name in OBJECTIVE_NAMES] == fixture["oracle"]["objective"]
    assert not validate_assignments(adapter["data"], result["assignments"])
    task_names = {value: key for key, value in adapter["task_ids"].items()}
    engineer_names = {value: key for key, value in adapter["engineer_ids"].items()}
    mapped = [{"task_id": task_names[row["order_id"]], "engineer_id": engineer_names[row["engineer_id"]],
               "start": row["start"], "end": row["end"]} for row in result["assignments"] if not row["locked"]]
    assert not validate_dispatch_solution(fixture["inputs"], mapped)
    assert adapter["boundary_excluded"] == fixture["oracle"]["excluded"]


def test_critical_priority_cannot_be_offset_by_routine_task():
    row = BY_ID["dispatch-critical-priority"]
    assert [item["task_id"] for item in row["oracle"]["assignments"]] == ["T2"]
    assert row["oracle"]["objective"][:6] == [0, 0, 0, 0, 1, 0]


def test_precedence_and_travel_have_manual_witnesses():
    precedence = BY_ID["dispatch-precedence"]["oracle"]["assignments"]
    assert precedence == [{"task_id": "T1", "engineer_id": "E1", "start": 0, "end": 10},
                          {"task_id": "T2", "engineer_id": "E1", "start": 10, "end": 20}]
    travel = {row["task_id"]: row for row in BY_ID["dispatch-travel-order"]["oracle"]["assignments"]}
    assert travel["T2"]["start"] == 0
    assert travel["T1"]["start"] == 15
    assert BY_ID["dispatch-travel-order"]["oracle"]["objective"][-2:] == [5, 0]


def test_shared_tool_and_locked_work_are_hard_constraints():
    fixture = BY_ID["dispatch-equipment-conflict"]
    bad = [{"task_id": "T1", "engineer_id": "E1", "start": 0, "end": 10},
           {"task_id": "T2", "engineer_id": "E2", "start": 0, "end": 10}]
    assert "tool_overlap:meter" in validate_dispatch_solution(fixture["inputs"], bad)
    locked = BY_ID["dispatch-started-task-locked"]
    reassigned = [{"task_id": "LOCK1", "engineer_id": "E2", "start": 0, "end": 15}]
    assert "locked_task_changed:LOCK1" in validate_dispatch_solution(locked["inputs"], reassigned)


@pytest.mark.parametrize("fixture_id,reason", [
    ("dispatch-pending-approval", "HUMAN_APPROVAL_REQUIRED"),
    ("dispatch-rejected-approval", "HUMAN_APPROVAL_REQUIRED"),
    ("dispatch-stale-approval", "STALE_APPROVAL_VERSION"),
    ("dispatch-stale-snapshot", "STALE_INPUT_VERSION"),
    ("dispatch-invalid-mapping", "INVALID_ASSET_MAPPING"),
    ("dispatch-stale-installation", "STALE_INSTALLATION_MAPPING"),
])
def test_fixture_service_preprocessing_rejects_unauthorized_or_stale_tasks(fixture_id, reason):
    fixture = BY_ID[fixture_id]
    assert fixture["oracle"]["assignments"] == []
    assert fixture["oracle"]["excluded"] == [{"task_id": "T1", "reason": reason}]
    bad = [{"task_id": "T1", "engineer_id": "E1", "start": 0, "end": 10}]
    assert "unapproved_or_unknown_task:T1" in validate_dispatch_solution(fixture["inputs"], bad)


def test_approval_idempotency_and_group_duplicate_boundary():
    duplicate = BY_ID["dispatch-duplicate-confirmation"]["oracle"]
    assert duplicate["idempotent_duplicate_task_ids"] == ["T1"]
    assert len(duplicate["assignments"]) == 1
    group = BY_ID["dispatch-group-work-order"]["oracle"]
    assert [row["task_id"] for row in group["assignments"]] == ["GROUP"]
    assert {row["task_id"] for row in group["excluded"]} == {"SINGLE_A", "SINGLE_B"}


def test_units_manufacturing_and_auxiliary_have_hand_computed_answers():
    assert BY_ID["carbon-wh-to-kwh"]["oracle"]["value"] == 1.25
    assert BY_ID["carbon-kg-to-tonne"]["oracle"]["value"] == 1.25
    assert BY_ID["carbon-manufacturing-per-pack"]["oracle"]["emission_kg"] == 200
    assert BY_ID["carbon-manufacturing-per-capacity"]["oracle"]["emission_kg"] == 200
    auxiliary = BY_ID["carbon-auxiliary-counted-once"]["oracle"]
    assert auxiliary == {"input_energy_kwh": 125., "aux_added_kwh": 0., "emission_kg": 62.5}


def test_same_service_preserves_positive_and_negative_sign():
    positive = BY_ID["carbon-same-service-positive-benefit"]["oracle"]
    negative = BY_ID["carbon-inefficiency-offsets-manufacturing"]["oracle"]
    assert math.isclose(positive["avoided_kg"], 275 / 9, abs_tol=1e-9)
    assert math.isclose(negative["avoided_kg"], -445 / 9, abs_tol=1e-9)
    assert not positive["permanent_avoidance_established"]
    assert negative["avoided_kg"] < 0


@pytest.mark.parametrize("gamma,expected", [(0, 0), (1, 20), (1.5, 25), (2, 30)])
def test_budget_support_against_hand_solution(gamma, expected):
    assert budget_support([20., -10.], gamma) == expected
    assert budget_support([-10., 20.], gamma) == expected


@pytest.mark.parametrize("fixture", [row for row in CARBON if row["kind"] == "robust_range"], ids=lambda fixture: fixture["fixture_id"])
def test_carbon_engine_budget_ranges_match_golden(fixture):
    from app.carbon.engine import robust_range

    data, expected = fixture["inputs"], fixture["oracle"]
    actual = robust_range(data["nominal"], {f"source-{index}": value for index, value in enumerate(data["coefficients"])}, data["gamma"])
    for key in ("nominal", "lower_under_set", "upper_under_set", "gamma", "approximation_error"):
        assert actual[key] == pytest.approx(expected[key], abs=1e-9, rel=1e-9)


@pytest.mark.parametrize("fixture", [row for row in CARBON if row["kind"] == "renewal"], ids=lambda fixture: fixture["fixture_id"])
def test_carbon_engine_renewal_matches_independent_golden(fixture):
    from app.carbon.engine import renewal_counts as runtime_renewal

    def duration_array(pmf):
        return [pmf.get(str(index), 0.) for index in range(1, max(map(int, pmf)) + 1)]

    data = fixture["inputs"]
    actual = runtime_renewal(duration_array(data["remaining_pmf"]), duration_array(data["new_lifetime_pmf"]), data["horizon"])
    assert not compare_expected({key: fixture["oracle"][key] for key in ("old", "new")}, actual)


@pytest.mark.parametrize("fixture", [row for row in CARBON if row["kind"] == "pareto"], ids=lambda fixture: fixture["fixture_id"])
def test_carbon_engine_pareto_matches_golden(fixture):
    from app.carbon.engine import pareto_front

    rows = [{"id": row["candidate_id"], "cost_nominal": row["cost"], "carbon_nominal": row["carbon"]}
            for row in fixture["inputs"]["candidates"] if row.get("feasible", True)]
    assert sorted(pareto_front(rows)) == fixture["oracle"]["frontier_ids"]


def test_shared_uncertainty_cancels_and_lower_benefit_can_be_negative():
    shared = BY_ID["carbon-shared-error-cancels"]["oracle"]
    assert shared["lower_avoided_kg"] == shared["nominal_avoided_kg"] == shared["upper_avoided_kg"] == 100
    negative = BY_ID["carbon-negative-robust-lower-benefit"]["oracle"]
    assert negative["lower_avoided_kg"] == -15
    assert not negative["robustly_better"]
    with pytest.raises(ValueError):
        budget_support([20., 10.], 3)


def test_renewal_counts_zero_once_multiple_and_distinct_remaining_life():
    assert BY_ID["carbon-zero-replacements"]["oracle"]["old"] == [0, 0, 0, 0, 0]
    assert BY_ID["carbon-one-replacement"]["oracle"]["old"] == [0, 0, 1, 1, 1]
    assert BY_ID["carbon-multiple-replacements"]["oracle"]["old"] == [0, 0, 1, 1, 2, 2, 3]
    # Residual-life and new-life distributions are intentionally different.
    counts = renewal_counts({"1": 1.}, {"3": 1.}, 4)
    assert counts["old"] == [0, 1, 1, 1, 2]
    assert counts["new"] == [0, 0, 0, 1, 1]
    with pytest.raises(ValueError):
        renewal_counts({"1": .8}, {"3": 1.}, 4)


def test_censored_lifetime_and_end_state_do_not_fabricate_benefit():
    censored = BY_ID["carbon-right-censored-life"]["oracle"]
    assert not censored["observed_eol"]
    assert censored["expected_remaining_cycles"] is None
    assert BY_ID["carbon-terminal-state-mismatch"]["oracle"]["avoided_kg"] is None
    reset = BY_ID["carbon-replacement-state-reset"]["oracle"]
    assert reset["terminal_distribution"] == [0, 1]
    assert reset["terminal_expected_age"] == 0
    assert not reset["old_installation_history_modified"]


def test_pareto_preserves_ties_and_filters_infeasible_candidates():
    assert BY_ID["carbon-pareto-dominance"]["oracle"] == {
        "frontier_ids": ["A", "C"], "dominated_ids": ["B"], "infeasible_ids": ["D"]}
    assert BY_ID["carbon-pareto-ties"]["oracle"]["frontier_ids"] == ["A", "B"]


def test_shadow_cash_and_correction_exports_remain_separate():
    unqualified = BY_ID["carbon-shadow-value-no-cash"]["oracle"]
    assert unqualified["shadow_value_rmb"] == 80
    assert unqualified["credit_cash_rmb"] is None
    assert unqualified["cash_status"] == "not_established"
    assert unqualified["total_cash_savings_rmb"] == 20
    qualified = BY_ID["carbon-qualified-demo-income-split"]["oracle"]
    assert qualified["credit_cash_rmb"] == 80
    assert qualified["total_cash_savings_rmb"] == 100  # Shadow value is not added.
    assert qualified["synthetic_rule_id"] == "TEST_RULE_001"
    export = BY_ID["carbon-correction-and-demo-export"]["oracle"]
    assert export["corrected_demo_emission_kg"] == 30
    assert export["formal_export_emission_kg"] == 0
    assert export["demo_export_marked_synthetic"]


def test_nonlinear_efficiency_and_unavailable_states_use_correct_service():
    nonlinear = BY_ID["carbon-nonlinear-efficiency-expectation"]["oracle"]
    assert math.isclose(nonlinear["expected_input_energy_kwh"], 1400 / 9, abs_tol=1e-9)
    assert nonlinear["invalid_shortcut_error_kwh"] > 12
    stopped = BY_ID["carbon-stopped-state-unmet-service"]["oracle"]
    assert stopped == {"expected_input_energy_kwh": 100., "unmet_service_kwh": 20., "service_feasible": False}


def test_validator_detects_provenance_numeric_and_domain_corruption(tmp_path):
    altered = copy.deepcopy(BY_ID["carbon-simple-electricity"])
    altered["synthetic"] = False
    altered["oracle"]["emission_kg"] = 0
    assert "missing_synthetic_demo_provenance" in validate_fixture(altered)
    assert any("emission_kg" in error for error in validate_fixture(altered))
    carbon_in_dispatch = copy.deepcopy(BY_ID["dispatch-basic"])
    carbon_in_dispatch["inputs"]["carbon_bonus"] = 100
    assert "carbon_in_dispatch_fixture" in validate_fixture(carbon_in_dispatch)
    generate_fixtures(tmp_path)
    path = tmp_path / "fixtures" / "carbon.jsonl"
    rows = path.read_text().splitlines()
    rows.append(rows[0])
    path.write_text("\n".join(rows) + "\n")
    assert any("duplicate_fixture_id" in error for error in validate_fixtures(tmp_path)["errors"])
    assert compare_expected({"metric": 1.}, {"metric": 1. + 1e-10}) == []
    assert compare_expected({"metric": 1.}, {"metric": float("nan")})
