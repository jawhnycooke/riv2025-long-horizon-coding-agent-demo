"""Agent definitions for Orchestrator + Worker architecture.

This module implements the two-agent pattern from Anthropic's
"Effective Harnesses for Long-Running Agents" article:
https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

Architecture:
    Orchestrator (sonnet) - Coordinates workflow, reads state, delegates tasks
    Worker (sonnet) - Executes atomic tasks (file ops, bash, testing)
"""

from src.agents.base import BaseAgentDefinition
from src.agents.worker import WorkerAgent, WORKER_PROMPT

# Lazy import for orchestrator to avoid import errors when claude_sdk not installed
def create_orchestrator_client(*args, **kwargs):
    """Create and configure the Orchestrator agent with Worker subagent.

    Lazy import wrapper to avoid module-level import of claude_sdk.
    """
    from src.agents.orchestrator import create_orchestrator_client as _create
    return _create(*args, **kwargs)


def create_legacy_client(*args, **kwargs):
    """Create the original monolithic client without subagents.

    Lazy import wrapper to avoid module-level import of claude_sdk.
    """
    from src.agents.orchestrator import create_legacy_client as _create
    return _create(*args, **kwargs)


__all__ = [
    "BaseAgentDefinition",
    "WorkerAgent",
    "WORKER_PROMPT",
    "create_orchestrator_client",
    "create_legacy_client",
]
