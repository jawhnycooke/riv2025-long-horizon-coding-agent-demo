"""Base agent definition class for SDK-native agent creation.

This module provides the BaseAgentDefinition dataclass that standardizes
how agents are defined programmatically using the Claude Agent SDK.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseAgentDefinition:
    """Base class for programmatic agent definitions.

    Provides a structured way to define agents that can be converted
    to Claude Agent SDK's AgentDefinition format.

    Attributes:
        name: Unique identifier for the agent (used in Task tool calls)
        description: Short description of what the agent does
        model: Model to use ("haiku", "sonnet", "opus")
        tools: List of tool names the agent can use
        system_prompt: The agent's system prompt

    Example:
        >>> agent = BaseAgentDefinition(
        ...     name="worker",
        ...     description="Executes atomic development tasks",
        ...     model="sonnet",
        ...     tools=["Read", "Write", "Edit", "Bash"],
        ...     system_prompt="You are a worker agent..."
        ... )
        >>> sdk_def = agent.to_sdk_definition()
    """

    name: str
    description: str
    model: str = "sonnet"
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""

    def to_sdk_definition(self) -> dict[str, Any]:
        """Convert to Claude Agent SDK AgentDefinition format.

        Returns:
            Dictionary compatible with SDK's agents parameter in ClaudeAgentOptions.

        Note:
            The SDK expects agents to be defined as a dict with the agent name
            as key and a dict containing description, prompt, tools, and model.
        """
        return {
            "description": self.description,
            "prompt": self.system_prompt,
            "tools": self.tools,
            "model": self.model,
        }

    def __post_init__(self) -> None:
        """Validate agent definition after initialization."""
        if not self.name:
            raise ValueError("Agent name is required")
        if not self.description:
            raise ValueError("Agent description is required")
        if self.model not in ("haiku", "sonnet", "opus"):
            raise ValueError(f"Invalid model: {self.model}. Must be haiku, sonnet, or opus")
