from __future__ import annotations

import torch
from torch import nn


class TargetScaledRegressor(nn.Module):
    """Train-only affine target scaling; inference still returns SOH ratios."""

    def __init__(self, backbone: nn.Module, mean: float, std: float) -> None:
        super().__init__()
        if not (torch.isfinite(torch.tensor(mean)) and torch.isfinite(torch.tensor(std))) or std <= 0:
            raise ValueError("Target scaling must be finite with positive standard deviation")
        self.backbone = backbone
        self.register_buffer("target_mean", torch.tensor(float(mean), dtype=torch.float32))
        self.register_buffer("target_std", torch.tensor(float(std), dtype=torch.float32))

    def forward(self, *args: torch.Tensor) -> torch.Tensor:
        return self.backbone(*args) * self.target_std + self.target_mean


class MLPRegressor(nn.Module):
    """Small feed-forward baseline for the same feature view."""

    def __init__(self, in_features: int, width: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(in_features, width), nn.ReLU(), nn.Linear(width, width), nn.ReLU(), nn.Linear(width, 1))

    def forward(self, current: torch.Tensor, reference: torch.Tensor, history: torch.Tensor, history_mask: torch.Tensor, condition: torch.Tensor | None = None) -> torch.Tensor:
        del reference, history, history_mask, condition
        return self.net(current).squeeze(-1)


class MLPMatched(nn.Module):
    """MLP baseline receiving the same current/reference/history summary view."""

    def __init__(self, in_features: int, width: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(in_features * 4 + 1, width), nn.ReLU(), nn.Linear(width, width), nn.ReLU(), nn.Linear(width, 1))

    def forward(self, current: torch.Tensor, reference: torch.Tensor, history: torch.Tensor, history_mask: torch.Tensor, condition: torch.Tensor | None = None) -> torch.Tensor:
        mask = history_mask.unsqueeze(-1)
        mean = (history * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
        slope = history[:, -1] - history[:, 0]
        quality = history_mask.mean(dim=1, keepdim=True) if condition is None else condition.reshape(-1, 1)
        view = torch.cat([current, reference, current - reference, mean + slope], dim=-1)
        return self.net(torch.cat([view, quality], dim=-1)).squeeze(-1)


class CPMLPLike(nn.Module):
    """A compact cycle/feature MLP baseline with explicit mask aggregation."""

    def __init__(self, in_features: int, width: int = 64) -> None:
        super().__init__()
        self.feature = nn.Sequential(nn.Linear(in_features, width), nn.GELU(), nn.Linear(width, width))
        self.cycle = nn.Sequential(nn.Linear(in_features, width), nn.GELU(), nn.Linear(width, width))
        self.head = nn.Sequential(nn.Linear(width * 2, width), nn.GELU(), nn.Linear(width, 1))

    def forward(self, current: torch.Tensor, reference: torch.Tensor, history: torch.Tensor, history_mask: torch.Tensor, condition: torch.Tensor | None = None) -> torch.Tensor:
        del condition
        current_z = self.feature(current - reference)
        mask = history_mask.unsqueeze(-1)
        hist_mean = (self.cycle(history) * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
        return self.head(torch.cat([current_z, hist_mean], dim=-1)).squeeze(-1)


class CADA(nn.Module):
    """Causal Anchored Degradation Adapter v0.

    This is a testable research hypothesis. The model only receives current and
    past tensors supplied by the Dataset; it has no access to future cycles.
    """

    def __init__(self, in_features: int, width: int = 64, use_anchor: bool = True, use_history: bool = True, use_condition_gate: bool = True) -> None:
        super().__init__()
        self.use_anchor = use_anchor
        self.use_history = use_history
        self.use_condition_gate = use_condition_gate
        self.current = nn.Sequential(nn.Linear(in_features, width), nn.GELU(), nn.Linear(width, width))
        self.reference = nn.Sequential(nn.Linear(in_features, width), nn.GELU(), nn.Linear(width, width))
        self.diff = nn.Sequential(nn.Linear(in_features, width), nn.GELU(), nn.Linear(width, width))
        self.history_conv = nn.Conv1d(in_features, width, kernel_size=3, dilation=1, padding=2)
        self.history_dilated = nn.Conv1d(width, width, kernel_size=3, dilation=2, padding=4)
        self.slow = nn.Sequential(nn.Linear(in_features * 2, width), nn.GELU(), nn.Linear(width, width))
        self.condition = nn.Sequential(nn.Linear(1, width), nn.Sigmoid())
        self.gate = nn.Sequential(nn.Linear(width * 3 + 1, width), nn.Sigmoid())
        self.head = nn.Sequential(nn.Linear(width, width), nn.GELU(), nn.Linear(width, 1))

    def forward(self, current: torch.Tensor, reference: torch.Tensor, history: torch.Tensor, history_mask: torch.Tensor, condition: torch.Tensor | None = None) -> torch.Tensor:
        cur = self.current(current)
        ref = self.reference(reference) if self.use_anchor else torch.zeros_like(cur)
        dif = self.diff(current - reference) if self.use_anchor else torch.zeros_like(cur)
        if self.use_history and history.shape[1]:
            mask = history_mask.unsqueeze(1)
            masked_history = history * mask.transpose(1, 2)
            h = torch.relu(self.history_conv(masked_history.transpose(1, 2)))
            h = torch.relu(self.history_dilated(h)[..., : history.shape[1]])
            h = (h * mask).sum(dim=-1) / mask.sum(dim=-1).clamp_min(1.0)
            valid_count = history_mask.sum(dim=1, keepdim=True).clamp_min(1.0)
            first = (history * mask.transpose(1, 2)).sum(dim=1) / valid_count
            last_index = (history_mask * torch.arange(history.shape[1], device=history.device, dtype=history_mask.dtype)).argmax(dim=1)
            last = history[torch.arange(history.shape[0], device=history.device), last_index]
            last = last * (history_mask.sum(dim=1, keepdim=True) > 0)
            slow = self.slow(torch.cat([first, last], dim=-1))
        else:
            h = torch.zeros_like(cur)
            slow = torch.zeros_like(cur)
        quality = history_mask.mean(dim=1, keepdim=True)
        if self.use_condition_gate:
            cond = torch.zeros_like(cur) if condition is None else self.condition(condition.reshape(-1, 1)) * cur
        else:
            cond = torch.zeros_like(cur)
        fused = cur + ref + dif + h + slow + cond
        gate = self.gate(torch.cat([cur, dif, h, quality], dim=-1))
        return self.head(fused * gate).squeeze(-1)
