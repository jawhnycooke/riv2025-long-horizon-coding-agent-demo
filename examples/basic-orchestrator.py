#!/usr/bin/env python3
"""
Basic Orchestrator + Worker Example

Demonstrates the two-agent pattern from Anthropic's
"Effective Harnesses for Long-Running Agents" article.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/basic-orchestrator.py
"""

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Agent Definitions
# =============================================================================


WORKER_PROMPT = """You are a worker agent that executes atomic tasks.

You receive specific, well-defined tasks from the orchestrator:
- File operations (create, edit, read files)
- Running commands (npm install, tests)
- Code modifications

Execute the task completely and return structured results.
Do NOT make high-level decisions - the orchestrator handles planning.

When done, summarize what you accomplished in a clear, concise format."""


ORCHESTRATOR_PROMPT = """You are an orchestrator agent that coordinates development work.

Your responsibilities:
1. Read state files to understand current progress
2. Select the next task to work on
3. Delegate atomic tasks to the Worker agent using the Task tool
4. Track progress and maintain session continuity

Session Startup Sequence:
1. Run `pwd` to confirm directory
2. Read progress files (tests.json, claude-progress.txt)
3. Check git log for recent commits
4. Select highest-priority pending feature
5. Delegate implementation to Worker

You have access to:
- Read, Glob, Grep: For reading state and exploring code
- Task: For delegating work to the Worker agent

Do NOT perform file modifications directly. Always delegate to Worker."""


@dataclass
class BaseAgentDefinition:
    """Base class for agent definitions."""

    name: str
    description: str
    model: str = "sonnet"
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""

    def to_sdk_definition(self) -> dict[str, Any]:
        """Convert to SDK-compatible definition."""
        return {
            "description": self.description,
            "prompt": self.system_prompt,
            "tools": self.tools,
            "model": self.model,
        }


@dataclass
class WorkerAgent(BaseAgentDefinition):
    """Worker agent that executes atomic tasks."""

    name: str = "worker"
    description: str = "Executes atomic development tasks"
    model: str = "sonnet"
    tools: list[str] = field(
        default_factory=lambda: [
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Glob",
            "Grep",
            "Bash",
        ]
    )
    system_prompt: str = WORKER_PROMPT


# =============================================================================
# Orchestrator Client Creation
# =============================================================================


def create_orchestrator_client(
    project_dir: str,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """
    Create an orchestrator client configuration.

    In the real implementation, this returns a ClaudeSDKClient.
    Here we return the configuration dict for demonstration.

    Args:
        project_dir: Path to the project directory
        model: Model to use for the orchestrator

    Returns:
        Configuration dictionary for the orchestrator
    """
    worker = WorkerAgent()

    return {
        "model": model,
        "system_prompt": ORCHESTRATOR_PROMPT,
        "allowed_tools": [
            "Read",  # Read state files
            "Glob",  # Find files
            "Grep",  # Search code
            "Task",  # Delegate to worker
        ],
        "agents": {
            worker.name: worker.to_sdk_definition(),
        },
        "cwd": project_dir,
    }


# =============================================================================
# Example Usage
# =============================================================================


def main() -> None:
    """Demonstrate orchestrator + worker pattern."""
    import json

    # Create configuration
    config = create_orchestrator_client(
        project_dir="/path/to/generated-app",
        model="claude-sonnet-4-20250514",
    )

    print("Orchestrator Configuration")
    print("=" * 50)
    print(json.dumps(config, indent=2, default=str))

    print("\n" + "=" * 50)
    print("How It Works")
    print("=" * 50)
    print(
        """
1. Orchestrator starts and reads state:
   - tests.json (feature status)
   - claude-progress.txt (session history)
   - git log (recent commits)

2. Orchestrator selects next task:
   - Finds highest priority pending feature
   - Formulates specific task for Worker

3. Orchestrator delegates via Task tool:
   Task(
       agent="worker",
       prompt="Implement the login form component..."
   )

4. Worker executes:
   - Uses Edit tool to modify files
   - Uses Bash for npm commands
   - Returns structured result

5. Orchestrator updates state:
   - Marks test as passing (if verified)
   - Updates progress log
   - Commits changes

6. Loop continues until all features done
"""
    )


if __name__ == "__main__":
    main()
