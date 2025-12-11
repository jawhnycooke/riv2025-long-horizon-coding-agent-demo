#!/usr/bin/env python3
"""Worker main entry point using harness-enforced architecture.

This is the entry point for the worker container in the two-container ECS
architecture. It uses the WorkerHarness to enforce structure around the
Claude agent, preventing common failure modes:

1. Premature Completion - Harness validates all tests pass
2. Incomplete Implementation - Harness assigns ONE feature per session
3. Inadequate Testing - Harness validates screenshot exists + was viewed
4. Inefficient Onboarding - Harness runs init.sh and smoke tests

The harness makes workflow decisions (what to build, when done).
The agent makes coding decisions (how to build).

Usage:
    python worker_main.py

Environment Variables (required):
    ISSUE_NUMBER: GitHub issue number being worked on
    GITHUB_REPOSITORY: GitHub repo in owner/repo format

Environment Variables (optional):
    AGENT_BRANCH: Git branch (default: agent-runtime)
    PROVIDER: anthropic or bedrock (default: anthropic)
    ENVIRONMENT: Environment name (default: reinvent)
    MAX_RETRIES_PER_TEST: Max retries per test (default: 3)
    SMOKE_TEST_TIMEOUT: Smoke test timeout seconds (default: 30)
    DEV_SERVER_PORT: Development server port (default: 6174)
    WORKSPACE_DIR: Base workspace directory (default: /app/workspace)
"""

import sys
from pathlib import Path

from src.cloudwatch_metrics import MetricsPublisher
from src.worker_config import WorkerConfig, WorkerStatus
from src.worker_harness import WorkerHarness


def load_system_prompt(repo_dir: Path) -> str:
    """Load the system prompt for the worker agent.

    Prefers the worker-specific system prompt (simplified for harness-based
    operation) over the generic system prompt.

    Args:
        repo_dir: Path to the cloned repository

    Returns:
        System prompt string
    """
    prompts_dir = repo_dir / "prompts"

    # Prefer worker-specific prompt (simplified for harness-based operation)
    worker_prompt_path = prompts_dir / "worker_system_prompt.txt"
    if worker_prompt_path.exists():
        print(f"📄 Using worker-specific system prompt: {worker_prompt_path}")
        return worker_prompt_path.read_text(encoding="utf-8")

    # Fall back to generic system prompt
    system_prompt_path = prompts_dir / "system_prompt.txt"
    if system_prompt_path.exists():
        print(f"📄 Using generic system prompt: {system_prompt_path}")
        return system_prompt_path.read_text(encoding="utf-8")

    # Fallback to a minimal system prompt for harness-based operation
    print("📄 Using minimal embedded system prompt")
    return """You are Claude Code, an expert software engineer.

You are implementing a specific test from tests.json. Your job is to:
1. Read and understand the test requirement
2. Implement the feature to make the test pass
3. Use Playwright MCP to take screenshots and verify your work
4. Mark the test as "pass" in tests.json when verified
5. Commit your changes

Tools available:
- File operations: Read, Write, Edit, Glob, Grep
- Commands: Bash (npm, git, playwright allowed)
- Browser: Playwright MCP (screenshot, click, fill, assert_visible)

Important rules:
- Focus ONLY on the assigned test
- Screenshot verification is REQUIRED before marking pass
- Commit when done or when stuck after multiple attempts
- Update claude-progress.txt with your progress
"""


def main() -> int:
    """Main entry point for the harness-based worker.

    Returns:
        Exit code:
            0 - Test passed, more tests remain (CONTINUE)
            1 - All tests pass (COMPLETE)
            2 - Unrecoverable error (FAILED)
            3 - Smoke test failed (BROKEN_STATE)
    """
    print("=" * 60)
    print("Worker - Harness-Enforced Architecture")
    print("=" * 60)

    # Initialize metrics publisher for heartbeats
    metrics = MetricsPublisher(enabled=True)

    # Load configuration from environment
    try:
        config = WorkerConfig.from_environment()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return WorkerStatus.FAILED.value

    # Create the harness
    harness = WorkerHarness(config)

    # Publish initial heartbeat
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # BEFORE Agent: Environment Setup
    # ==========================================================================

    print("\n--- Phase 1: Environment Setup ---")

    if not harness.setup_environment():
        print("Environment setup failed")
        return WorkerStatus.FAILED.value

    # Publish heartbeat after setup
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # BEFORE Agent: Start Dev Servers
    # ==========================================================================

    print("\n--- Phase 2: Start Dev Servers ---")

    if not harness.start_dev_servers():
        print("Dev server startup failed")
        return WorkerStatus.FAILED.value

    # Publish heartbeat after servers start
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # BEFORE Agent: Smoke Test
    # ==========================================================================

    print("\n--- Phase 3: Smoke Test ---")

    if not harness.run_smoke_test():
        print("Smoke test failed - application is in broken state")
        return WorkerStatus.BROKEN_STATE.value

    # ==========================================================================
    # BEFORE Agent: Task Selection
    # ==========================================================================

    print("\n--- Phase 4: Task Selection ---")

    task = harness.select_next_task()
    if not task:
        print("All tests pass - nothing to do!")
        return WorkerStatus.COMPLETE.value

    # ==========================================================================
    # DURING Agent: Run Agent Session
    # ==========================================================================

    print("\n--- Phase 5: Agent Session ---")
    print(f"Assigned task: {task.id}")
    print(f"Description: {task.description}")

    # Build the focused prompt
    prompt = harness.build_agent_prompt(task)

    # Load system prompt
    system_prompt = load_system_prompt(config.repo_dir)

    # Create the agent client
    client = harness.create_agent_client(system_prompt)

    # Run the agent
    try:
        print("\nStarting Claude agent...")
        result = client.process(prompt)
        print(f"\nAgent session completed: {result}")
    except KeyboardInterrupt:
        print("\nAgent interrupted by user")
    except Exception as e:
        print(f"\nAgent error: {e}")
        import traceback
        traceback.print_exc()

    # Publish heartbeat after agent completes
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # AFTER Agent: Validate Results
    # ==========================================================================

    print("\n--- Phase 6: Validation ---")

    # Check if a commit was made
    commit_made = harness.verify_commit_made()

    # Determine exit status (harness decides, not agent)
    status = harness.determine_exit_status()

    # Push changes if commit was made
    if commit_made:
        harness.push_changes()

    # ==========================================================================
    # Exit with appropriate status
    # ==========================================================================

    print("\n" + "=" * 60)
    print(f"Worker Exit Status: {status.name} ({status.value})")
    print("=" * 60)

    return status.value


if __name__ == "__main__":
    sys.exit(main())
