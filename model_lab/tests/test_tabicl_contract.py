import numpy as np
import pytest

from model_lab.scripts.evaluate_tabicl import positive_exp, query_isolation
from model_lab.scripts.train_nested_cv import matched


class IndependentQuery:
    def predict(self, x):
        return np.asarray(x)[:, 0] * .01 - .1


class CrossQueryLeak:
    def predict(self, x):
        return np.asarray(x)[:, 0] * .01 - .1 + np.asarray(x)[:, 0].mean()


def test_query_batch_isolation_accepts_independent_function():
    result = query_isolation(IndependentQuery(), np.arange(12).reshape(3, 4))
    assert result['max_log_prediction_difference'] == 0


def test_query_batch_isolation_rejects_cross_query_features():
    with pytest.raises(RuntimeError, match='isolation'):
        query_isolation(CrossQueryLeak(), np.arange(12).reshape(3, 4))


def test_nonfinite_or_overflow_predictions_do_not_become_success():
    for bad in ([np.nan], [np.inf], [10000.], [-10000.]):
        with pytest.raises((ValueError, FloatingPointError)):
            positive_exp(np.array(bad))


def test_reference_calibration_view_and_identity():
    r = np.arange(15, dtype=np.float32).reshape(3, 5)
    anchor = matched(r, r, np.zeros(3, dtype=np.float32))
    assert anchor.shape == (3, 16)
    np.testing.assert_equal(anchor[:, 10:], 0.)
    fixed_log_prediction = IndependentQuery().predict(anchor)
    np.testing.assert_equal(positive_exp(fixed_log_prediction-fixed_log_prediction), 1.)
