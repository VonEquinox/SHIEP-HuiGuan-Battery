"""Small reference-conditioned, identity-anchored log-SOH model."""
from __future__ import annotations

import torch
from torch import nn


class AnchoredConditionalResidual(nn.Module):
    def __init__(self, dimension: int, width: int = 24, rank: int = 4):
        super().__init__()
        self.linear = nn.Linear(dimension, 1, bias=False)
        nn.init.zeros_(self.linear.weight)
        self.u = nn.Parameter(torch.randn(dimension, rank) * .02)
        self.v = nn.Parameter(torch.randn(dimension, rank) * .02)
        self.residual = nn.Sequential(
            nn.Linear(2 * dimension, width), nn.GELU(), nn.Linear(width, 1)
        )
        nn.init.zeros_(self.residual[-1].weight)
        nn.init.zeros_(self.residual[-1].bias)
        self.rank = rank

    def components(self, current: torch.Tensor, reference: torch.Tensor):
        delta = current - reference
        linear = self.linear(delta)
        bilinear = ((delta @ self.u) * (reference @ self.v)).sum(-1, keepdim=True) / self.rank
        here = self.residual(torch.cat((current, reference), dim=-1))
        at_reference = self.residual(torch.cat((reference, reference), dim=-1))
        nonlinear = .1 * (here - at_reference)
        return linear, bilinear, nonlinear

    def forward(self, current: torch.Tensor, reference: torch.Tensor):
        return sum(self.components(current, reference))
