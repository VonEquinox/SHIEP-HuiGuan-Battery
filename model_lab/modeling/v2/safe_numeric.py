"""Validate numerical M1 JSON recipes before interpreting them.

This is a data validator, never a deserializer for Python objects. The limits
bound each exported ensemble and the aggregate model, including input JSON size.
All numerical leaves must be native JSON numbers; coercion is deliberately absent.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass


MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSON_VALUES = 3_000_000
MAX_JSON_DEPTH = 64
MAX_DOMAINS = 64
MAX_FEATURES = 4096
MAX_TREE_NODES = 65_535
MAX_TOTAL_NODES = 250_000
MAX_TOTAL_TREES = 8192
MAX_ITERATIONS = 1024
MAX_GRID_LENGTH = 512


class NumericModelValidationError(ValueError):
    """An exported numerical recipe has an unsafe or inconsistent value."""


def _fail(path: str, message: str) -> None:
    raise NumericModelValidationError(f"{path}: {message}")


def _json_preflight(value) -> None:
    """Count JSON bytes iteratively, without recursive serialization or coercion."""
    # Iterator frames keep auxiliary memory proportional to nesting depth, even
    # for an input array with millions of scalar entries.
    pending = [(iter((value,)), 0)]
    size = count = 0
    while pending:
        iterator, depth = pending[-1]
        try:
            item = next(iterator)
        except StopIteration:
            pending.pop()
            continue
        count += 1
        if count > MAX_JSON_VALUES or depth > MAX_JSON_DEPTH:
            _fail("model", "JSON value/depth budget exceeded")
        if type(item) is dict:
            if len(item) > MAX_JSON_VALUES - count:
                _fail("model", "JSON value budget exceeded")
            size += 2 + max(0, len(item) - 1)
            for key in item:
                if type(key) is not str:
                    _fail("model", "JSON object keys must be strings")
                if len(key) > MAX_JSON_BYTES:
                    _fail("model", "JSON byte budget exceeded")
                size += len(json.dumps(key, ensure_ascii=True)) + 1
                if size > MAX_JSON_BYTES:
                    _fail("model", "JSON byte budget exceeded")
            pending.append((iter(item.values()), depth + 1))
        elif type(item) is list:
            size += 2 + max(0, len(item) - 1)
            # Check length before expanding a potentially hostile array.
            if len(item) > MAX_JSON_VALUES - count:
                _fail("model", "JSON value budget exceeded")
            pending.append((iter(item), depth + 1))
        elif type(item) is str:
            if len(item) > MAX_JSON_BYTES:
                _fail("model", "JSON byte budget exceeded")
            size += len(json.dumps(item, ensure_ascii=True))
        elif type(item) is bool or item is None:
            size += 4 if item is None or item is True else 5
        elif type(item) is int:
            if item.bit_length() > 1024:
                _fail("model", "integer magnitude budget exceeded")
            size += len(str(item))
        elif type(item) is float:
            if not math.isfinite(item):
                _fail("model", "non-finite JSON number")
            size += len(json.dumps(item, allow_nan=False))
        else:
            _fail("model", "only native JSON objects, arrays, and scalars are accepted")
        if size > MAX_JSON_BYTES:
            _fail("model", "JSON byte budget exceeded")


def _object(value, path: str, required: set[str], optional: set[str] | None = None):
    if type(value) is not dict:
        _fail(path, "object required")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing:
        _fail(path, f"missing fields: {sorted(missing)}")
    if extra:
        _fail(path, f"unknown fields: {sorted(extra)}")
    return value


def _array(value, path: str, minimum: int, maximum: int):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail(path, f"array length must be in [{minimum}, {maximum}]")
    return value


def _number(value, path: str):
    if type(value) not in (int, float):
        _fail(path, "finite native int/float required (no booleans or strings)")
    # The int bit-length bound also avoids OverflowError in math.isfinite.
    if type(value) is int and value.bit_length() > 1024:
        _fail(path, "integer magnitude budget exceeded")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        _fail(path, "finite native int/float required")
    return value


def _integer(value, path: str, minimum: int, maximum: int):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(path, f"native integer in [{minimum}, {maximum}] required")
    return value


def _text(value, path: str, *, maximum=4096):
    if type(value) is not str or not value or len(value) > maximum:
        _fail(path, f"nonempty string of at most {maximum} characters required")
    return value


def _feature_width(n_features):
    if n_features is not None:
        _integer(n_features, "n_features", 1, MAX_FEATURES)
    return n_features


@dataclass
class _Budget:
    nodes: int = 0
    trees: int = 0

    def add_tree(self, nodes: int, path: str):
        self.nodes += nodes
        self.trees += 1
        if self.nodes > MAX_TOTAL_NODES or self.trees > MAX_TOTAL_TREES:
            _fail(path, "aggregate tree/node budget exceeded")


def _tree(tree, path: str, n_features: int | None, budget: _Budget) -> None:
    _object(tree, path, {"children_left", "children_right", "feature", "threshold", "value"})
    left = _array(tree["children_left"], f"{path}.children_left", 1, MAX_TREE_NODES)
    n = len(left)
    budget.add_tree(n, path)
    for key in ("children_right", "feature", "threshold", "value"):
        _array(tree[key], f"{path}.{key}", n, n)
    right, features = tree["children_right"], tree["feature"]
    parent_count = [0] * n
    width = n_features if n_features is not None else MAX_FEATURES
    for node in range(n):
        l = _integer(left[node], f"{path}.children_left[{node}]", -1, n - 1)
        r = _integer(right[node], f"{path}.children_right[{node}]", -1, n - 1)
        f = _integer(features[node], f"{path}.feature[{node}]", -2, width - 1)
        _number(tree["threshold"][node], f"{path}.threshold[{node}]")
        row = _array(tree["value"][node], f"{path}.value[{node}]", 1, 1)
        _number(row[0], f"{path}.value[{node}][0]")
        if l == -1 or r == -1:
            if l != -1 or r != -1 or f != -2:
                _fail(path, "leaves require two -1 children and sklearn's -2 feature sentinel")
        else:
            if f < 0:
                _fail(path, "branch feature must be a nonnegative in-range index")
            for child in (l, r):
                parent_count[child] += 1
                if parent_count[child] > 1:
                    _fail(path, "a tree node cannot have multiple parents")
    if parent_count[0] != 0:
        _fail(path, "root cannot have a parent (cycle)")
    # Iteration prevents malformed deep trees from overflowing Python's stack.
    pending, visited = [0], set()
    while pending:
        node = pending.pop()
        if node in visited:
            _fail(path, "tree cycle or repeated node")
        visited.add(node)
        if left[node] != -1:
            pending.extend((left[node], right[node]))
    if len(visited) != n:
        _fail(path, "all nodes must be reachable from root; disconnected cycle/node")


def _gb(model, path: str, n_features: int | None, budget: _Budget) -> None:
    _object(model, path, {"kind", "initial", "learning_rate", "trees"})
    if model["kind"] not in ("gradient_boosting", "binary_gradient_boosting"):
        _fail(f"{path}.kind", "gradient boosting recipe required")
    _number(model["initial"], f"{path}.initial")
    if _number(model["learning_rate"], f"{path}.learning_rate") <= 0:
        _fail(f"{path}.learning_rate", "positive learning rate required")
    trees = _array(model["trees"], f"{path}.trees", 1, MAX_ITERATIONS)
    for i, tree in enumerate(trees):
        _tree(tree, f"{path}.trees[{i}]", n_features, budget)


def _ngboost(model, path: str, n_features: int | None, budget: _Budget) -> None:
    _object(model, path, {"kind", "initial", "learning_rate", "scalings", "columns", "trees"})
    if model["kind"] != "ngboost_normal":
        _fail(f"{path}.kind", "NGBoost Normal recipe required")
    initial = _array(model["initial"], f"{path}.initial", 2, 2)
    for i, value in enumerate(initial):
        _number(value, f"{path}.initial[{i}]")
    if _number(model["learning_rate"], f"{path}.learning_rate") <= 0:
        _fail(f"{path}.learning_rate", "positive learning rate required")
    trees = _array(model["trees"], f"{path}.trees", 1, MAX_ITERATIONS)
    n = len(trees)
    _array(model["scalings"], f"{path}.scalings", n, n)
    _array(model["columns"], f"{path}.columns", n, n)
    for i, iteration in enumerate(trees):
        if _number(model["scalings"][i], f"{path}.scalings[{i}]") < 0:
            _fail(f"{path}.scalings[{i}]", "nonnegative scale required")
        columns = _array(model["columns"][i], f"{path}.columns[{i}]", 1, n_features or MAX_FEATURES)
        for j, column in enumerate(columns):
            _integer(column, f"{path}.columns[{i}][{j}]", 0, (n_features or MAX_FEATURES) - 1)
        if len(set(columns)) != len(columns):
            _fail(f"{path}.columns[{i}]", "feature columns must be unique")
        _array(iteration, f"{path}.trees[{i}]", 2, 2)
        for j, tree in enumerate(iteration):
            _tree(tree, f"{path}.trees[{i}][{j}]", len(columns), budget)


def _grid(value, path: str):
    grid = _array(value, path, 1, MAX_GRID_LENGTH)
    previous = 0
    for i, endpoint in enumerate(grid):
        endpoint = _number(endpoint, f"{path}[{i}]")
        if endpoint <= previous:
            _fail(path, "positive, strictly increasing grid required")
        previous = endpoint
    return grid


def _survival(model, path: str, n_features: int | None, expected_grid=None) -> None:
    _object(model, path, {"grid", "coef", "intercept", "fit_status"})
    grid = _grid(model["grid"], f"{path}.grid")
    if expected_grid is not None and grid != expected_grid:
        _fail(f"{path}.grid", "must match the baseline survival grid")
    coef = _array(model["coef"], f"{path}.coef", n_features or 1, n_features or MAX_FEATURES)
    for i, value in enumerate(coef):
        _number(value, f"{path}.coef[{i}]")
    intercept = _array(model["intercept"], f"{path}.intercept", len(grid), len(grid))
    for i, value in enumerate(intercept):
        _number(value, f"{path}.intercept[{i}]")
    status = _object(model["fit_status"], f"{path}.fit_status", {"success", "message", "nll_regularized"})
    if type(status["success"]) is not bool:
        _fail(f"{path}.fit_status.success", "JSON boolean required")
    _text(status["message"], f"{path}.fit_status.message")
    if _number(status["nll_regularized"], f"{path}.fit_status.nll_regularized") < 0:
        _fail(f"{path}.fit_status.nll_regularized", "nonnegative loss required")


def _task(model, path: str, n_features: int | None, budget: _Budget) -> None:
    if type(model) is not dict or model.get("support") not in ("supported", "unsupported"):
        _fail(path, "supported/unsupported task object required")
    if model["support"] == "unsupported":
        _object(model, path, {"support", "reason"})
        _text(model["reason"], f"{path}.reason")
        return
    _object(model, path, {"support", "quantiles"}, {"distribution"})
    quantiles = _object(model["quantiles"], f"{path}.quantiles", {"0.05", "0.5", "0.95"})
    for q, recipe in quantiles.items():
        _gb(recipe, f"{path}.quantiles[{q}]", n_features, budget)
        if recipe["kind"] != "gradient_boosting":
            _fail(f"{path}.quantiles[{q}].kind", "scalar regression required")
    if "distribution" in model:
        _ngboost(model["distribution"], f"{path}.distribution", n_features, budget)


def validate_tree_dict(tree, *, n_features: int | None = None) -> None:
    """Validate one scalar sklearn tree without converting any values."""
    _json_preflight(tree)
    _tree(tree, "tree", _feature_width(n_features), _Budget())


def validate_gb_dict(model, *, n_features: int | None = None) -> None:
    """Validate scalar regression or binary-logit boosting at an inference boundary."""
    _json_preflight(model)
    _gb(model, "gb", _feature_width(n_features), _Budget())


def validate_ngboost_dict(model, *, n_features: int | None = None) -> None:
    _json_preflight(model)
    _ngboost(model, "ngboost", _feature_width(n_features), _Budget())


def validate_survival_dict(model, *, n_features: int | None = None) -> None:
    _json_preflight(model)
    _survival(model, "survival", _feature_width(n_features))


def validate_baseline_dict(model, *, n_features: int | None = None) -> None:
    """Validate an M1 DomainBaseline export, including every source-specific head.

    Old exports without ``min_survival_objects``/``survival_support`` remain valid.
    Present support receipts must agree with the presence and independent-object
    requirement of the corresponding fitted survival head.
    """
    _json_preflight(model)
    n_features = _feature_width(n_features)
    _object(model, "baseline", {"kind", "seed", "survival_grid", "domains"}, {"min_survival_objects"})
    if model["kind"] != "M1":
        _fail("baseline.kind", "M1 recipe required")
    _integer(model["seed"], "baseline.seed", 0, 2**32 - 1)
    grid = _grid(model["survival_grid"], "baseline.survival_grid")
    minimum = _integer(model.get("min_survival_objects", 1), "baseline.min_survival_objects", 1, MAX_JSON_VALUES)
    domains = model["domains"]
    if type(domains) is not dict or not 1 <= len(domains) <= MAX_DOMAINS:
        _fail("baseline.domains", f"between 1 and {MAX_DOMAINS} domain objects required")
    budget = _Budget()
    for domain, heads in domains.items():
        _text(domain, "baseline.domain", maximum=384)
        if len(domain.split("::")) != 3 or any(not part for part in domain.split("::")):
            _fail("baseline.domain", "source::chemistry::protocol identity required")
        path = f"baseline.domains[{domain}]"
        _object(heads, path, {"soh", "efficiency"}, {"fault", "survival", "survival_support"})
        for task in ("soh", "efficiency"):
            _task(heads[task], f"{path}.{task}", n_features, budget)
        if "fault" in heads:
            _gb(heads["fault"], f"{path}.fault", n_features, budget)
            if heads["fault"]["kind"] != "binary_gradient_boosting":
                _fail(f"{path}.fault.kind", "binary gradient boosting required")
        if "survival" in heads:
            _survival(heads["survival"], f"{path}.survival", n_features, grid)
        if "survival_support" in heads:
            receipt = _object(heads["survival_support"], f"{path}.survival_support",
                              {"independent_training_objects", "minimum_training_objects", "status", "reason"})
            count = _integer(receipt["independent_training_objects"], f"{path}.survival_support.independent_training_objects", 0, MAX_JSON_VALUES)
            required = _integer(receipt["minimum_training_objects"], f"{path}.survival_support.minimum_training_objects", 1, MAX_JSON_VALUES)
            if required != minimum:
                _fail(f"{path}.survival_support", "object requirement must match baseline configuration")
            if receipt["status"] == "supported":
                if "survival" not in heads or count < required or receipt["reason"] is not None:
                    _fail(f"{path}.survival_support", "supported receipt contradicts fitted head/count/reason")
            elif receipt["status"] == "unsupported":
                _text(receipt["reason"], f"{path}.survival_support.reason")
                if "survival" in heads or count >= required:
                    _fail(f"{path}.survival_support", "unsupported receipt contradicts fitted head/count")
            else:
                _fail(f"{path}.survival_support.status", "supported/unsupported status required")
