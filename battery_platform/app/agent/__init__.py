"""Public V2 single-Agent service interfaces, independent of DB and API routes."""

from .context import ContextConflict, ContextStore, evolve_context
from .contracts import AgentReport, EDITABLE_SKILL_FIELDS, TOOL_WHITELIST, public_context, validate_report
from .executor import AgentExecutor, run_agent
from .feedback import extract_feedback
from .llm import LLMError, OpenAICompatibleClient
from .skills import SkillLibrary
from .tools import ToolError, ToolRegistry
from .evaluation import ARMS, GEPASearch, ReplayEvaluator, score_report, validate_skill_candidate
from .gepa_service import DevSelectionScorer, GEPAService, make_batch_optimizer

__all__ = ["AgentExecutor", "AgentReport", "ContextConflict", "ContextStore", "EDITABLE_SKILL_FIELDS",
           "LLMError", "OpenAICompatibleClient", "SkillLibrary", "TOOL_WHITELIST", "ToolError",
           "ToolRegistry", "evolve_context", "extract_feedback", "public_context", "run_agent", "validate_report",
           "ARMS", "GEPASearch", "ReplayEvaluator", "score_report", "validate_skill_candidate",
           "DevSelectionScorer", "GEPAService", "make_batch_optimizer"]
