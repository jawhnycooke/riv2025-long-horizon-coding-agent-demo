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

from claude_agent_sdk import (
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ProcessError,
)

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

You are implementing a specific feature from feature_list.json. Your job is to:
1. Read and understand the feature requirement
2. Implement the feature to make the test pass
3. Use Playwright MCP to take screenshots and verify your work
4. Mark the feature as passing (set "passes": true) in feature_list.json when verified
5. Commit your changes

Tools available:
- File operations: Read, Write, Edit, Glob, Grep
- Commands: Bash (npm, git, playwright allowed)
- Browser: Playwright MCP (screenshot, click, fill, assert_visible)

Important rules:
- Focus ONLY on the assigned feature
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
    print("[WORKER] 🔨 Harness-Enforced Architecture")
    print("=" * 60)

    # Initialize metrics publisher for heartbeats
    metrics = MetricsPublisher(enabled=True)

    # Load configuration from environment
    try:
        config = WorkerConfig.from_environment()
    except ValueError as e:
        print(f"[WORKER] ❌ Configuration error: {e}")
        return WorkerStatus.FAILED.value

    # Create the harness
    harness = WorkerHarness(config)

    # Publish initial heartbeat
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # BEFORE Agent: Environment Setup
    # ==========================================================================

    print("\n[WORKER] --- Phase 1: Environment Setup ---")

    if not harness.setup_environment():
        print("[WORKER] ❌ Environment setup failed")
        return WorkerStatus.FAILED.value

    # Publish heartbeat after setup
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # BEFORE Agent: Start Dev Servers
    # ==========================================================================

    print("\n[WORKER] --- Phase 2: Start Dev Servers ---")

    if not harness.start_dev_servers():
        print("[WORKER] ❌ Dev server startup failed")
        return WorkerStatus.FAILED.value

    # Publish heartbeat after servers start
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # BEFORE Agent: Smoke Test
    # ==========================================================================

    print("\n[WORKER] --- Phase 3: Smoke Test ---")

    if not harness.run_smoke_test():
        print("[WORKER] ❌ Smoke test failed - application is in broken state")
        return WorkerStatus.BROKEN_STATE.value

    # ==========================================================================
    # BEFORE Agent: Feature List Generation (First Run)
    # ==========================================================================

    print("\n[WORKER] --- Phase 4: Feature List ---")

    if not harness.ensure_feature_list_exists():
        print("[WORKER] ❌ Failed to create or find feature_list.json")
        return WorkerStatus.FAILED.value

    # ==========================================================================
    # BEFORE Agent: Task Selection
    # ==========================================================================

    print("\n[WORKER] --- Phase 5: Task Selection ---")

    task = harness.select_next_task()
    if not task:
        if harness.all_tests_exhausted:
            print("[WORKER] ❌ All failing tests have exhausted retries")
            return WorkerStatus.FAILED.value
        print("[WORKER] ✅ All tests pass - nothing to do!")
        return WorkerStatus.COMPLETE.value

    # ==========================================================================
    # DURING Agent: Run Agent Session
    # ==========================================================================

    print("\n[WORKER] --- Phase 6: Agent Session ---")
    print(f"[WORKER] 📌 Assigned task: {task.id}")
    print(f"[WORKER] 📝 Description: {task.description}")

    # Build the focused prompt
    prompt = harness.build_agent_prompt(task)

    # Load system prompt
    system_prompt = load_system_prompt(config.repo_dir)

    # Create the agent client
    client = harness.create_agent_client(system_prompt)

    # Run the agent
    try:
        print("\n[WORKER] 🚀 Starting Claude agent...")
        result = client.process(prompt)
        print(f"\n[WORKER] 📋 Agent session completed: {result}")
    except CLINotFoundError:
        print("\n[WORKER] ❌ Claude Code CLI not found")
        print("[WORKER]    Install: npm install -g @anthropic-ai/claude-code")
        return WorkerStatus.FAILED.value
    except CLIConnectionError as e:
        print(f"\n[WORKER] ❌ Failed to connect to Claude Code: {e}")
        return WorkerStatus.FAILED.value
    except ProcessError as e:
        print(f"\n[WORKER] ❌ Claude Code process failed (exit code {e.exit_code}): {e}")
        return WorkerStatus.FAILED.value
    except CLIJSONDecodeError as e:
        print(f"\n[WORKER] ❌ Failed to parse response from Claude Code: {e}")
        return WorkerStatus.FAILED.value
    except KeyboardInterrupt:
        print("\n[WORKER] ⚠️ Agent interrupted by user")
    except ClaudeSDKError as e:
        print(f"\n[WORKER] ❌ SDK error: {e}")
        return WorkerStatus.FAILED.value
    except Exception as e:
        print(f"\n[WORKER] ❌ Unexpected agent error: {e}")
        import traceback
        traceback.print_exc()

    # Publish heartbeat after agent completes
    metrics.publish_session_heartbeat()

    # ==========================================================================
    # AFTER Agent: Validate Results
    # ==========================================================================

    print("\n[WORKER] --- Phase 7: Validation ---")

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
    print(f"[WORKER] Exit Status: {status.name} ({status.value})")
    print("=" * 60)

    return status.value


if __name__ == "__main__":
    sys.exit(main())
