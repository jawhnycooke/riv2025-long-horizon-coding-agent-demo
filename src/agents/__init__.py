"""Agent client factory for Claude SDK.

This module provides the create_agent_client function for creating
a configured ClaudeSDKClient with security hooks and tracing.
"""


# Lazy import to avoid import errors when claude_sdk not installed
def create_agent_client(*args, **kwargs):
    """Create and configure the Claude agent client.

    Lazy import wrapper to avoid module-level import of claude_sdk.
    """
    from src.agents.orchestrator import create_agent_client as _create
    return _create(*args, **kwargs)


__all__ = [
    "create_agent_client",
]
