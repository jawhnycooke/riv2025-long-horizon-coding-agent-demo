#!/usr/bin/env python3
"""
Basic Claude Agent Example

Demonstrates creating a Claude Agent SDK client with security hooks
for long-horizon coding sessions.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/basic-agent.py
"""

from typing import Any


# =============================================================================
# Agent Configuration
# =============================================================================


AGENT_PROMPT = """You are a coding agent that builds React applications.

Your responsibilities:
1. Read state files to understand current progress
2. Select the next task to work on
3. Implement features following the build plan
4. Run tests and verify with screenshots
5. Commit changes and update progress

Session Startup Sequence:
1. Run `pwd` to confirm directory
2. Read progress files (tests.json, claude-progress.txt)
3. Check git log for recent commits
4. Select highest-priority pending feature
5. Implement and test the feature

Available tools:
- Read, Write, Edit, MultiEdit: File operations
- Glob, Grep: Search and exploration
- Bash: Run commands (npm, playwright, git)

Always verify your work with screenshots before marking tests as passing."""


# =============================================================================
# Agent Client Creation
# =============================================================================


def create_agent_client(
    project_dir: str,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """
    Create a Claude agent client configuration.

    In the real implementation, this returns a ClaudeSDKClient.
    Here we return the configuration dict for demonstration.

    Args:
        project_dir: Path to the project directory
        model: Model to use

    Returns:
        Configuration dictionary for the agent
    """
    return {
        "model": model,
        "system_prompt": AGENT_PROMPT,
        "allowed_tools": [
            "think",      # Reasoning
            "Read",       # Read files
            "Write",      # Write files
            "Edit",       # Edit files
            "MultiEdit",  # Bulk edits
            "Glob",       # Find files
            "Grep",       # Search content
            "Bash",       # Run commands
        ],
        "cwd": project_dir,
    }


# =============================================================================
# Security Hook Example
# =============================================================================


async def path_security_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None = None,
    context: Any = None,
    project_root: str = "",
) -> dict[str, Any]:
    """
    Security hook to validate file paths are within project.

    Args:
        input_data: Tool input data
        tool_use_id: Unique tool use identifier
        context: Additional context
        project_root: Root directory for path validation

    Returns:
        Modified input data (or raises exception if blocked)
    """
    tool_input = input_data.get("tool_input", {})

    # Check for file_path parameter
    file_path = tool_input.get("file_path", "")
    if file_path and not file_path.startswith(project_root):
        raise ValueError(f"Path {file_path} is outside project root")

    return input_data


# =============================================================================
# Example Usage
# =============================================================================


def main() -> None:
    """Demonstrate basic agent pattern."""
    import json

    # Create configuration
    config = create_agent_client(
        project_dir="/path/to/generated-app",
        model="claude-sonnet-4-20250514",
    )

    print("Agent Configuration")
    print("=" * 50)
    print(json.dumps(config, indent=2, default=str))

    print("\n" + "=" * 50)
    print("How It Works")
    print("=" * 50)
    print(
        """
1. Agent starts and reads state:
   - tests.json (feature status)
   - claude-progress.txt (session history)
   - git log (recent commits)

2. Agent selects next task:
   - Finds highest priority pending feature
   - Plans implementation approach

3. Agent implements feature:
   - Uses Edit tool to modify files
   - Uses Bash for npm commands
   - Takes screenshots for verification

4. Agent verifies and commits:
   - Runs E2E tests
   - Marks tests as passing (if verified)
   - Updates progress log
   - Commits changes

5. Loop continues until all features done
"""
    )


if __name__ == "__main__":
    main()
