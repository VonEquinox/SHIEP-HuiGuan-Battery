"""Deterministic dispatch: the LLM proposes, CP-SAT schedules, humans assign."""

from .solver import solve, validate_assignments

__all__ = ["solve", "validate_assignments"]
