"""Reference-conditioned RBF difference kernel with exact reference identity."""
from __future__ import annotations

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from sklearn.metrics.pairwise import rbf_kernel


class ConditionalDifferenceKernel:
    def __init__(self, alpha: float, gamma: float):
        self.alpha = alpha
        self.gamma = gamma

    def kernel(self, x, reference, z, other_reference):
        a = np.concatenate((x, reference), axis=1)
        b = np.concatenate((reference, reference), axis=1)
        c = np.concatenate((z, other_reference), axis=1)
        d = np.concatenate((other_reference, other_reference), axis=1)
        return (rbf_kernel(a, c, gamma=self.gamma)
                - rbf_kernel(a, d, gamma=self.gamma)
                - rbf_kernel(b, c, gamma=self.gamma)
                + rbf_kernel(b, d, gamma=self.gamma))

    def fit(self, x, reference, log_soh, sample_weight):
        self.x = np.asarray(x, dtype=np.float64).copy()
        self.reference = np.asarray(reference, dtype=np.float64).copy()
        self.scale = max(float(np.std(log_soh)), .02)
        root_weight = np.sqrt(sample_weight)
        gram = self.kernel(self.x, self.reference, self.x, self.reference)
        system = gram * root_weight[:, None] * root_weight[None, :]
        system.flat[::len(system) + 1] += self.alpha
        self.coef = root_weight * cho_solve(
            cho_factor(system, lower=True, check_finite=True),
            root_weight * (np.asarray(log_soh) / self.scale))
        return self

    def predict_log(self, x, reference):
        return self.scale * (self.kernel(x, reference, self.x, self.reference) @ self.coef)
