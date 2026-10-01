"""Malformed numerical recipes fail before NumPy coercion or tree execution."""
from copy import deepcopy

import pytest

from model_lab.modeling.v2 import safe_numeric as safe


def tree():
    return {"children_left": [1, -1, -1], "children_right": [2, -1, -1],
            "feature": [0, -2, -2], "threshold": [0.25, -2.0, -2.0],
            "value": [[0.0], [0.2], [-0.1]]}


def gb(kind="gradient_boosting"):
    return {"kind": kind, "initial": 0.1, "learning_rate": 0.05, "trees": [tree()]}


def ngboost():
    return {"kind": "ngboost_normal", "initial": [0.0, -1.0], "learning_rate": 0.03,
            "scalings": [1.0], "columns": [[1, 0]], "trees": [[tree(), tree()]]}


def baseline():
    task = {"support": "supported", "quantiles": {q: gb() for q in ("0.05", "0.5", "0.95")},
            "distribution": ngboost()}
    return {"kind": "M1", "seed": 0, "survival_grid": [50, 100],
            "domains": {"matr::LFP::policy-a": {"soh": task,
                         "efficiency": {"support": "unsupported", "reason": "no_verified_labels"},
                         "fault": gb("binary_gradient_boosting")}}}


def survival():
    return {"grid": [50, 100], "coef": [0.1, -0.2], "intercept": [-2.0, -3.0],
            "fit_status": {"success": True, "message": "converged", "nll_regularized": 0.3}}


def test_valid_export_is_accepted_without_mutation():
    model = baseline()
    original = deepcopy(model)
    safe.validate_baseline_dict(model, n_features=2)
    assert model == original


@pytest.mark.parametrize("field,index,value", [
    ("threshold", 0, "0.25"), ("threshold", 0, True), ("threshold", 0, float("nan")),
    ("children_left", 0, "1"), ("children_left", 0, 1.0),
    ("feature", 0, True), ("feature", 0, 2),
])
def test_tree_rejects_coercible_and_out_of_range_values(field, index, value):
    bad = tree()
    bad[field][index] = value
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_tree_dict(bad, n_features=2)


@pytest.mark.parametrize("value", ["0.2", False, float("inf"), [0.2], None])
def test_tree_value_must_be_one_finite_native_number(value):
    bad = tree()
    bad["value"][1] = [value]
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_tree_dict(bad)


@pytest.mark.parametrize("mutation", [
    lambda t: t["threshold"].pop(),
    lambda t: t["value"].__setitem__(1, [0.1, 0.2]),
    lambda t: t["children_left"].__setitem__(0, 3),
    lambda t: t["children_right"].__setitem__(0, 1),
    lambda t: t["children_left"].__setitem__(0, 0),
    lambda t: t["children_right"].__setitem__(1, 2),
])
def test_malformed_tree_shapes_edges_and_cycles_fail(mutation):
    bad = tree()
    mutation(bad)
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_tree_dict(bad)


def test_disconnected_subtree_is_rejected():
    bad = tree()
    for field in ("children_left", "children_right", "feature", "threshold", "value"):
        bad[field].append([-0.2] if field == "value" else -2 if field in ("feature", "threshold") else -1)
    with pytest.raises(safe.NumericModelValidationError, match="reachable"):
        safe.validate_tree_dict(bad)


def test_deep_tree_validation_is_iterative():
    depth = 1500
    n = depth * 2 + 1
    bad = {"children_left": [-1] * n, "children_right": [-1] * n,
           "feature": [-2] * n, "threshold": [-2.0] * n, "value": [[0.0] for _ in range(n)]}
    for node in range(depth):
        bad["children_left"][node] = node + 1
        bad["children_right"][node] = depth + 1 + node
        bad["feature"][node] = 0
        bad["threshold"][node] = 0.5
    safe.validate_tree_dict(bad, n_features=1)


@pytest.mark.parametrize("mutation", [
    lambda m: m.__setitem__("initial", "0.1"),
    lambda m: m.__setitem__("learning_rate", True),
    lambda m: m.__setitem__("learning_rate", 0.0),
    lambda m: m.__setitem__("trees", []),
])
def test_boosting_boundary_rejects_bad_scalar_recipes(mutation):
    bad = gb()
    mutation(bad)
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_gb_dict(bad, n_features=2)


@pytest.mark.parametrize("mutation", [
    lambda m: m.__setitem__("initial", [0.0]),
    lambda m: m["initial"].__setitem__(0, "0.0"),
    lambda m: m.__setitem__("scalings", []),
    lambda m: m["scalings"].__setitem__(0, "1.0"),
    lambda m: m.__setitem__("columns", [[0, 0]]),
    lambda m: m.__setitem__("columns", [[2]]),
    lambda m: m["trees"][0].pop(),
])
def test_ngboost_iterations_and_columns_have_consistent_shapes(mutation):
    bad = ngboost()
    mutation(bad)
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_ngboost_dict(bad, n_features=2)


@pytest.mark.parametrize("mutation", [
    lambda m: m.__setitem__("grid", [50, 50]),
    lambda m: m.__setitem__("grid", ["50", 100]),
    lambda m: m.__setitem__("coef", [0.1]),
    lambda m: m["coef"].__setitem__(0, True),
    lambda m: m.__setitem__("intercept", [-1.0]),
    lambda m: m["fit_status"].__setitem__("success", "true"),
    lambda m: m["fit_status"].__setitem__("nll_regularized", "0.3"),
])
def test_survival_grid_dimensions_and_status_are_strict(mutation):
    bad = survival()
    mutation(bad)
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_survival_dict(bad, n_features=2)


def test_domain_tasks_and_support_receipts_are_consistent():
    model = baseline()
    model["min_survival_objects"] = 2
    heads = model["domains"]["matr::LFP::policy-a"]
    heads["survival"] = survival()
    heads["survival_support"] = {"independent_training_objects": 3, "minimum_training_objects": 2,
                                 "status": "supported", "reason": None}
    safe.validate_baseline_dict(model, n_features=2)
    heads["survival_support"]["independent_training_objects"] = 1
    with pytest.raises(safe.NumericModelValidationError, match="contradicts"):
        safe.validate_baseline_dict(model, n_features=2)


@pytest.mark.parametrize("mutation", [
    lambda m: m.__setitem__("seed", False),
    lambda m: m.__setitem__("seed", "0"),
    lambda m: m["domains"]["matr::LFP::policy-a"]["soh"]["quantiles"].pop("0.05"),
    lambda m: m["domains"]["matr::LFP::policy-a"]["efficiency"].__setitem__("quantiles", {}),
    lambda m: m["domains"].__setitem__("invalid-domain", m["domains"].pop("matr::LFP::policy-a")),
])
def test_baseline_refuses_ambiguous_domain_or_task_contracts(mutation):
    bad = baseline()
    mutation(bad)
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_baseline_dict(bad)


def test_iteration_node_and_byte_budgets(monkeypatch):
    monkeypatch.setattr(safe, "MAX_ITERATIONS", 1)
    bad = gb()
    bad["trees"].append(tree())
    with pytest.raises(safe.NumericModelValidationError):
        safe.validate_gb_dict(bad)
    monkeypatch.setattr(safe, "MAX_TOTAL_NODES", 2)
    with pytest.raises(safe.NumericModelValidationError, match="budget"):
        safe.validate_tree_dict(tree())
    monkeypatch.setattr(safe, "MAX_JSON_BYTES", 32)
    with pytest.raises(safe.NumericModelValidationError, match="byte budget"):
        safe.validate_gb_dict(gb())


def test_non_json_containers_and_recursive_values_fail():
    bad = tree()
    bad["threshold"] = tuple(bad["threshold"])
    with pytest.raises(safe.NumericModelValidationError, match="native JSON"):
        safe.validate_tree_dict(bad)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(safe.NumericModelValidationError, match="depth budget"):
        safe.validate_tree_dict(cycle)
