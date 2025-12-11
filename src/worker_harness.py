"""Worker harness for harness-enforced agent architecture.

This module implements the harness pattern from Anthropic's "Effective Harnesses
for Long-Running Agents" article, enforcing structure around the Claude agent
to prevent common failure modes:

1. Premature Completion - Harness validates all tests pass
2. Incomplete Implementation - Harness assigns ONE feature per session
3. Inadequate Testing - Harness validates screenshot exists + was viewed
4. Inefficient Onboarding - Harness runs init.sh and smoke tests

The harness makes workflow decisions (what to build, when done).
The agent makes coding decisions (how to build).
"""

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from src.config import Provider, apply_provider_config
from src.secrets import get_anthropic_api_key, get_github_token
from src.security import SecurityValidator
from src.worker_config import TestTask, WorkerConfig, WorkerStatus


class WorkerHarness:
    """Harness that enforces structure around the Claude agent.

    The harness handles:
    - Environment setup (clone, branch, servers)
    - Task selection (picks ONE failing test)
    - Agent execution (creates focused prompt)
    - Result validation (checks test status, commits)
    """

    def __init__(self, config: WorkerConfig):
        """Initialize the worker harness.

        Args:
            config: Worker configuration
        """
        self.config = config
        self.assigned_task: TestTask | None = None
        self.session_start_time: datetime | None = None
        self.github_token: str | None = None

    # =========================================================================
    # BEFORE Agent
    # =========================================================================

    def setup_environment(self) -> bool:
        """Set up the working environment.

        - Get GitHub token
        - Clone or update repository
        - Checkout agent branch

        Returns:
            True if setup successful, False otherwise
        """
        print("=" * 60)
        print("🔧 Worker Harness - Environment Setup")
        print("=" * 60)
        print(f"📋 Issue: #{self.config.issue_number}")
        print(f"📦 Repository: {self.config.github_repo}")
        print(f"🌿 Branch: {self.config.branch}")

        # Get GitHub token
        self.github_token = get_github_token(self.config.github_repo)
        if not self.github_token:
            print("❌ Failed to get GitHub token")
            return False

        # Ensure workspace exists
        self.config.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Clone or update repository
        if not self._clone_or_update_repo():
            return False

        # Checkout branch
        if not self._checkout_branch():
            return False

        print("✅ Environment setup complete")
        return True

    def _clone_or_update_repo(self) -> bool:
        """Clone repository or pull latest changes."""
        repo_dir = self.config.repo_dir
        clone_url = f"https://x-access-token:{self.github_token}@github.com/{self.config.github_repo}.git"

        if repo_dir.exists():
            print(f"📂 Repository exists at {repo_dir}")
            try:
                subprocess.run(
                    ["git", "fetch", "origin"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️ Failed to fetch: {e}")
                return False
        else:
            print(f"📥 Cloning repository to {repo_dir}...")
            try:
                subprocess.run(
                    ["git", "clone", clone_url, str(repo_dir)],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ Clone failed: {e.stderr.decode() if e.stderr else e}")
                return False

    def _checkout_branch(self) -> bool:
        """Create or checkout the agent branch."""
        repo_dir = self.config.repo_dir
        branch = self.config.branch

        try:
            # Check if branch exists remotely
            result = subprocess.run(
                ["git", "branch", "-r", "--list", f"origin/{branch}"],
                cwd=repo_dir,
                capture_output=True,
                timeout=30,
            )
            branch_exists = bool(result.stdout.strip())

            if branch_exists:
                print(f"🌿 Checking out existing branch: {branch}")
                subprocess.run(
                    ["git", "checkout", branch],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                subprocess.run(
                    ["git", "pull", "origin", branch],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
            else:
                print(f"🌿 Creating new branch: {branch}")
                subprocess.run(
                    ["git", "checkout", "-b", branch],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )

            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Branch operation failed: {e}")
            return False

    def start_dev_servers(self) -> bool:
        """Start development servers using init.sh.

        Returns:
            True if servers started successfully
        """
        init_script = self.config.init_script_path

        if not init_script.exists():
            print("⚠️ No init.sh found - skipping server startup")
            return True

        print("🚀 Starting development servers...")
        try:
            # Run init.sh in background
            subprocess.Popen(
                ["bash", str(init_script)],
                cwd=self.config.repo_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for server to be ready
            return self._wait_for_server()
        except Exception as e:
            print(f"❌ Failed to start servers: {e}")
            return False

    def _wait_for_server(self, timeout: int = 60) -> bool:
        """Wait for development server to be ready."""
        import socket

        url = self.config.dev_server_address
        port = self.config.dev_server_port

        print(f"⏳ Waiting for server at {url}...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                sock.close()
                if result == 0:
                    print(f"✅ Server ready at {url}")
                    return True
            except Exception:
                pass
            time.sleep(1)

        print(f"❌ Server not ready after {timeout}s")
        return False

    def run_smoke_test(self) -> bool:
        """Run a basic smoke test to verify the app isn't broken.

        Returns:
            True if smoke test passes
        """
        print("🧪 Running smoke test...")

        try:
            # Simple check: can we load the main page?
            result = subprocess.run(
                [
                    "npx", "playwright", "screenshot",
                    self.config.dev_server_address,
                    "/tmp/smoke-test.png",
                ],
                cwd=self.config.repo_dir,
                capture_output=True,
                timeout=self.config.smoke_test_timeout,
            )

            if result.returncode == 0:
                print("✅ Smoke test passed")
                return True
            else:
                print(f"❌ Smoke test failed: {result.stderr.decode()}")
                return False
        except subprocess.TimeoutExpired:
            print("❌ Smoke test timed out")
            return False
        except Exception as e:
            print(f"❌ Smoke test error: {e}")
            return False

    def select_next_task(self) -> TestTask | None:
        """Select the next failing test to work on.

        Returns:
            TestTask if a failing test found, None if all pass
        """
        tests_path = self.config.tests_json_path

        if not tests_path.exists():
            print("⚠️ No tests.json found")
            return None

        try:
            with open(tests_path) as f:
                tests_data = json.load(f)

            # Find first failing test
            for test_data in tests_data:
                if test_data.get("status") != "pass":
                    task = TestTask.from_dict(test_data)

                    # Check retry limit
                    if task.retry_count >= self.config.max_retries_per_test:
                        print(f"⏭️ Skipping {task.id} - max retries reached")
                        continue

                    self.assigned_task = task
                    print(f"📌 Selected task: {task.id}")
                    print(f"   Description: {task.description}")
                    return task

            print("✅ All tests pass - nothing to do")
            return None

        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ Error reading tests.json: {e}")
            return None

    # =========================================================================
    # DURING Agent
    # =========================================================================

    def build_agent_prompt(self, task: TestTask) -> str:
        """Build a focused prompt for the agent.

        Args:
            task: The test task to implement

        Returns:
            Focused prompt string
        """
        # Load project context
        build_plan_summary = self._load_build_plan_summary()
        progress_context = self._load_progress_context()

        return f"""## Your Task

Implement this ONE feature:

**Test ID:** {task.id}
**Description:** {task.description}

**Steps to verify:**
{task.steps}

## Tools Available

- **File operations:** Read, Write, Edit, Glob, Grep
- **Commands:** Bash (npm, git, playwright allowed)
- **Browser:** Playwright MCP (screenshot, click, fill, assert_visible)

## Process

1. Understand the requirement from the description and steps
2. Implement the feature
3. Test with Playwright MCP:
   - Take a screenshot
   - Verify the expected behavior visually
   - Check for console errors
4. Fix any issues you find
5. Mark test as "pass" in tests.json using the Edit tool
6. Commit your changes with a descriptive message

## Constraints

- Work ONLY on this test - do not touch other features
- Screenshot verification is REQUIRED before marking pass
- Commit when done (or when stuck after 3 attempts)
- If stuck, update claude-progress.txt with what you tried

## Project Context

{build_plan_summary}

## Previous Progress

{progress_context}

## Issue Context

Working on GitHub Issue #{self.config.issue_number}
Branch: {self.config.branch}

Begin implementing {task.id} now.
"""

    def _load_build_plan_summary(self) -> str:
        """Load a summary of BUILD_PLAN.md."""
        build_plan_path = self.config.repo_dir / "prompts" / "BUILD_PLAN.md"

        if not build_plan_path.exists():
            # Try alternate location
            build_plan_path = self.config.repo_dir / "BUILD_PLAN.md"

        if not build_plan_path.exists():
            return "[No BUILD_PLAN.md found]"

        try:
            content = build_plan_path.read_text(encoding="utf-8")
            # Return first 2000 chars as summary
            if len(content) > 2000:
                return content[:2000] + "\n\n[... truncated ...]"
            return content
        except Exception as e:
            return f"[Error loading BUILD_PLAN.md: {e}]"

    def _load_progress_context(self) -> str:
        """Load progress context from claude-progress.txt."""
        progress_path = self.config.progress_file_path

        if not progress_path.exists():
            return "[No previous progress recorded]"

        try:
            content = progress_path.read_text(encoding="utf-8")
            # Return last 1000 chars
            if len(content) > 1000:
                return "..." + content[-1000:]
            return content
        except Exception as e:
            return f"[Error loading progress: {e}]"

    def create_agent_client(self, system_prompt: str) -> ClaudeSDKClient:
        """Create the Claude SDK client with Playwright MCP.

        Args:
            system_prompt: System prompt for the agent

        Returns:
            Configured ClaudeSDKClient
        """
        project_root = str(self.config.repo_dir)

        # Apply provider configuration
        if self.config.provider == "bedrock":
            os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
            apply_provider_config(Provider.BEDROCK)
        else:
            apply_provider_config(Provider.ANTHROPIC)

        # Get API key if using Anthropic
        if self.config.provider == "anthropic":
            api_key = get_anthropic_api_key()
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

        # MCP servers - Playwright for browser automation
        mcp_servers = {
            "playwright": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server-playwright"],
            },
        }

        # Security hook wrappers
        async def path_hook(input_data: dict, tool_use_id: str | None = None, context: Any = None):
            return await SecurityValidator.universal_path_security_hook(
                input_data, tool_use_id, context, project_root
            )

        async def bash_hook(input_data: dict, tool_use_id: str | None = None, context: Any = None):
            return await SecurityValidator.bash_security_hook(
                input_data, tool_use_id, context, project_root
            )

        async def read_hook(input_data: dict, tool_use_id: str | None = None, context: Any = None):
            return await SecurityValidator.track_read_hook(
                input_data, tool_use_id, context, project_root
            )

        from claude_agent_sdk.types import HookMatcher

        return ClaudeSDKClient(
            options=ClaudeAgentOptions(
                model="claude-sonnet-4-20250514",
                system_prompt=system_prompt,
                mcp_servers=mcp_servers,
                allowed_tools=[
                    "Read", "Write", "Edit", "Glob", "Grep",
                    "Bash", "MultiEdit", "think",
                    "mcp__playwright__*",  # Playwright MCP tools
                ],
                hooks={
                    "PreToolUse": [
                        HookMatcher(matcher="*", hooks=[path_hook]),
                    ],
                    "PostToolUse": [
                        HookMatcher(matcher="Bash", hooks=[bash_hook]),
                        HookMatcher(matcher="Read", hooks=[read_hook]),
                    ],
                },
                max_turns=1000,  # Per-task limit
                cwd=project_root,
            )
        )

    # =========================================================================
    # AFTER Agent
    # =========================================================================

    def verify_commit_made(self) -> bool:
        """Verify that a git commit was made during the session.

        Returns:
            True if commit was made
        """
        try:
            # Check git log for recent commits
            result = subprocess.run(
                ["git", "log", "--oneline", "-1", "--since=1 hour ago"],
                cwd=self.config.repo_dir,
                capture_output=True,
                timeout=10,
            )
            has_commit = bool(result.stdout.strip())

            if has_commit:
                print(f"✅ Commit found: {result.stdout.decode().strip()}")
            else:
                print("⚠️ No commit made in this session")

            return has_commit
        except Exception as e:
            print(f"⚠️ Could not verify commit: {e}")
            return False

    def check_test_status(self) -> str:
        """Check the status of the assigned test in tests.json.

        Returns:
            Test status: "pass", "fail", or "unknown"
        """
        if not self.assigned_task:
            return "unknown"

        tests_path = self.config.tests_json_path

        try:
            with open(tests_path) as f:
                tests_data = json.load(f)

            for test in tests_data:
                if test.get("id") == self.assigned_task.id:
                    status = test.get("status", "fail")
                    print(f"📊 Test {self.assigned_task.id} status: {status}")
                    return status

            return "unknown"
        except Exception as e:
            print(f"⚠️ Could not check test status: {e}")
            return "unknown"

    def increment_retry_count(self) -> None:
        """Increment retry count for the assigned test in tests.json."""
        if not self.assigned_task:
            return

        tests_path = self.config.tests_json_path

        try:
            with open(tests_path) as f:
                tests_data = json.load(f)

            for test in tests_data:
                if test.get("id") == self.assigned_task.id:
                    test["retry_count"] = test.get("retry_count", 0) + 1
                    break

            with open(tests_path, "w") as f:
                json.dump(tests_data, f, indent=2)

        except Exception as e:
            print(f"⚠️ Could not update retry count: {e}")

    def determine_exit_status(self) -> WorkerStatus:
        """Determine the worker exit status based on test results.

        The harness (not the agent) decides when work is complete.

        Returns:
            WorkerStatus indicating what should happen next
        """
        # Check if assigned test passed
        test_status = self.check_test_status()

        if test_status != "pass":
            # Test didn't pass - increment retry and continue
            self.increment_retry_count()

            if self.assigned_task and self.assigned_task.retry_count >= self.config.max_retries_per_test:
                print(f"❌ Test {self.assigned_task.id} failed after {self.config.max_retries_per_test} attempts")
                return WorkerStatus.FAILED

            print(f"🔄 Test not yet passing - will retry")
            return WorkerStatus.CONTINUE

        # Test passed - check if all tests pass
        tests_path = self.config.tests_json_path

        try:
            with open(tests_path) as f:
                tests_data = json.load(f)

            all_pass = all(t.get("status") == "pass" for t in tests_data)

            if all_pass:
                print("🎉 ALL TESTS PASS - IMPLEMENTATION COMPLETE")
                return WorkerStatus.COMPLETE
            else:
                print("✅ Test passed - more tests remain")
                return WorkerStatus.CONTINUE

        except Exception as e:
            print(f"⚠️ Could not check all tests: {e}")
            return WorkerStatus.CONTINUE

    def push_changes(self) -> bool:
        """Push committed changes to remote.

        Returns:
            True if push successful
        """
        try:
            subprocess.run(
                ["git", "push", "-u", "origin", self.config.branch],
                cwd=self.config.repo_dir,
                check=True,
                capture_output=True,
                timeout=60,
            )
            print(f"✅ Pushed to origin/{self.config.branch}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Push failed: {e}")
            return False
