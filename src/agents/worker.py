"""Worker agent definition for atomic task execution.

The Worker agent is the "hands" of the system - it executes specific,
well-defined tasks delegated by the Orchestrator. This maps to the
"Coding Agent" role in Anthropic's article pattern, focused on
incremental feature development.

Design Principles:
    1. Atomic tasks only - no high-level planning
    2. Structured results - return outcomes the Orchestrator can use
    3. Full tool access - can read, write, edit, and run commands
    4. Screenshot verification - follows the test verification workflow
"""

from src.agents.base import BaseAgentDefinition


# Worker prompt - kept simple and focused on task execution
WORKER_PROMPT = """You are a Worker agent that executes atomic development tasks.

## Your Role
You receive specific, well-defined tasks from the Orchestrator. Execute them completely and return structured results. Do NOT make high-level decisions - the Orchestrator handles planning.

## Task Types You Handle
- **File Operations**: Create, edit, read files
- **Commands**: Run npm, playwright, git, and other allowed commands
- **Testing**: Execute E2E tests, capture screenshots, verify UI
- **Code Modifications**: Implement features, fix bugs, refactor code

## Execution Guidelines

### For File Operations
1. Read files before editing to understand context
2. Make targeted changes - don't refactor unrelated code
3. Preserve existing patterns and style

### For Testing
1. Use playwright-screenshot.js for screenshot verification
2. Always use `--operation full` to capture both screenshot AND console
3. Read BOTH the screenshot AND console log before marking tests
4. Follow the test verification workflow exactly

### For Commands
1. Check command success via exit codes
2. Capture and report errors
3. Don't retry failed commands without Orchestrator guidance

## Response Format
When completing a task, provide:
1. **Status**: SUCCESS or FAILURE
2. **Actions Taken**: List of what you did
3. **Results**: Output, files modified, test outcomes
4. **Issues**: Any problems encountered (for FAILURE status)

## Important Rules
- Execute ONE task at a time
- Don't start new features without Orchestrator delegation
- Report blockers immediately rather than guessing
- Never modify tests.json without proper screenshot verification
"""


class WorkerAgent(BaseAgentDefinition):
    """Worker subagent for atomic task execution.

    This agent has full tool access to execute development tasks:
    - File operations (Read, Write, Edit, MultiEdit)
    - Search (Glob, Grep)
    - Commands (Bash)
    - Reasoning (think)

    The Worker focuses on execution, not planning. It receives
    specific tasks from the Orchestrator and returns structured results.
    """

    def __init__(self) -> None:
        """Initialize the Worker agent with default configuration."""
        super().__init__(
            name="worker",
            description="Executes atomic development tasks including file operations, commands, and testing",
            model="sonnet",
            tools=[
                # File operations
                "Read",
                "Write",
                "Edit",
                "MultiEdit",
                # Search
                "Glob",
                "Grep",
                # Commands
                "Bash",
                # Reasoning
                "think",
            ],
            system_prompt=WORKER_PROMPT,
        )


def get_worker_agent() -> WorkerAgent:
    """Factory function to create a Worker agent instance.

    Returns:
        Configured WorkerAgent instance.
    """
    return WorkerAgent()
