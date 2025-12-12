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

from src.config import Provider, apply_provider_config, get_model_id
from src.secrets import (
    BEDROCK_API_KEY_ENV_VAR,
    get_anthropic_api_key,
    get_bedrock_api_key,
    get_github_token,
)
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
        self.all_tests_exhausted: bool = False

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
        print("[WORKER] 🔧 Harness - Environment Setup")
        print("=" * 60)
        print(f"[WORKER] 📋 Issue: #{self.config.issue_number}")
        print(f"[WORKER] 📦 Repository: {self.config.github_repo}")
        print(f"[WORKER] 🌿 Branch: {self.config.branch}")

        # Get GitHub token
        self.github_token = get_github_token(self.config.github_repo)
        if not self.github_token:
            print("[WORKER] ❌ Failed to get GitHub token")
            return False

        # Ensure workspace exists
        self.config.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Clone or update repository
        if not self._clone_or_update_repo():
            return False

        # Checkout branch
        if not self._checkout_branch():
            return False

        print("[WORKER] ✅ Environment setup complete")
        return True

    def _clone_or_update_repo(self) -> bool:
        """Clone repository or pull latest changes."""
        repo_dir = self.config.repo_dir
        clone_url = f"https://x-access-token:{self.github_token}@github.com/{self.config.github_repo}.git"

        if repo_dir.exists():
            print(f"[WORKER] 📂 Repository exists at {repo_dir}")
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
                print(f"[WORKER] ⚠️ Failed to fetch: {e}")
                return False
        else:
            print(f"[WORKER] 📥 Cloning repository to {repo_dir}...")
            try:
                subprocess.run(
                    ["git", "clone", clone_url, str(repo_dir)],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"[WORKER] ❌ Clone failed: {e.stderr.decode() if e.stderr else e}")
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
                print(f"[WORKER] 🌿 Checking out existing branch: {branch}")
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
                print(f"[WORKER] 🌿 Creating new branch: {branch}")
                subprocess.run(
                    ["git", "checkout", "-b", branch],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )

            return True
        except subprocess.CalledProcessError as e:
            print(f"[WORKER] ❌ Branch operation failed: {e}")
            return False

    def start_dev_servers(self) -> bool:
        """Start development servers using init.sh.

        Returns:
            True if servers started successfully
        """
        init_script = self.config.init_script_path

        if not init_script.exists():
            print("[WORKER] ⚠️ No init.sh found - skipping server startup")
            return True

        print("[WORKER] 🚀 Starting development servers...")
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
            print(f"[WORKER] ❌ Failed to start servers: {e}")
            return False

    def _wait_for_server(self, timeout: int = 60) -> bool:
        """Wait for development server to be ready."""
        import socket

        url = self.config.dev_server_address
        port = self.config.dev_server_port

        print(f"[WORKER] ⏳ Waiting for server at {url}...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                sock.close()
                if result == 0:
                    print(f"[WORKER] ✅ Server ready at {url}")
                    return True
            except Exception:
                pass
            time.sleep(1)

        print(f"[WORKER] ❌ Server not ready after {timeout}s")
        return False

    def run_smoke_test(self) -> bool:
        """Run a basic smoke test to verify the app isn't broken.

        Returns:
            True if smoke test passes
        """
        print("[WORKER] 🧪 Running smoke test...")

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
                print("[WORKER] ✅ Smoke test passed")
                return True
            else:
                print(f"[WORKER] ❌ Smoke test failed: {result.stderr.decode()}")
                return False
        except subprocess.TimeoutExpired:
            print("[WORKER] ❌ Smoke test timed out")
            return False
        except Exception as e:
            print(f"[WORKER] ❌ Smoke test error: {e}")
            return False

    def ensure_feature_list_exists(self) -> bool:
        """Generate feature_list.json if it doesn't exist.

        On first worker run for an issue, generates a comprehensive feature list
        from BUILD_PLAN.md. Subsequent runs use the existing file.

        Returns:
            True if feature list exists or was generated successfully
        """
        if self.config.feature_list_path.exists():
            print("[WORKER] ✅ feature_list.json exists")
            return True

        print("[WORKER] 📝 Generating feature_list.json (first run)...")
        return self._run_initialization_agent()

    def _run_initialization_agent(self) -> bool:
        """Run a Claude agent to generate feature_list.json from BUILD_PLAN.md."""
        # Load initialization prompt
        init_prompt = self._load_initialization_prompt()

        # Create agent client (reuse existing method)
        client = self.create_agent_client(init_prompt)

        # Run agent to generate feature list
        try:
            client.process(self._build_init_task_prompt())
            if self.config.feature_list_path.exists():
                print("[WORKER] ✅ feature_list.json generated successfully")
                return True
            else:
                print("[WORKER] ❌ feature_list.json was not created")
                return False
        except Exception as e:
            print(f"[WORKER] ❌ Failed to generate feature list: {e}")
            return False

    def _load_initialization_prompt(self) -> str:
        """Load the initialization system prompt."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "initialization_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return self._default_initialization_prompt()

    def _default_initialization_prompt(self) -> str:
        """Return default initialization system prompt if file not found."""
        return """You are an expert software architect generating a comprehensive feature list.

Your task is to analyze the BUILD_PLAN.md specification and create a
feature_list.json file with 50-200 test cases that will guide implementation.

## Guidelines

1. **Order matters**: Start with foundational features (setup, auth, basic CRUD)
   then progress to advanced features (real-time, integrations, edge cases)

2. **Atomic features**: Each test should represent ONE implementable feature
   that can be verified with a screenshot

3. **Clear verification**: The "steps" field should describe exactly how to
   verify the feature works (what to click, what to see)

4. **Coverage**: Ensure tests cover:
   - All pages/routes in the application
   - All user interactions (forms, buttons, navigation)
   - Error states and edge cases
   - Responsive/mobile behavior
   - Accessibility requirements

5. **IDs**: Use kebab-case IDs that describe the feature
   Good: "user-can-login", "sidebar-collapse-on-mobile"
   Bad: "test1", "feature_a"

Write the feature_list.json file using the Write tool.
"""

    def _build_init_task_prompt(self) -> str:
        """Build the task prompt for initialization."""
        build_plan = self._load_build_plan_summary()
        return f"""Generate a comprehensive feature_list.json for this project.

## Project Specification (BUILD_PLAN.md)
{build_plan}

## Output Requirements
Create feature_list.json with 50-200 test cases covering:
1. Core functionality (authentication, navigation, CRUD operations)
2. UI/UX features (responsive design, accessibility, error states)
3. Edge cases and error handling
4. Integration points

## JSON Format
```json
[
  {{
    "id": "unique-kebab-case-id",
    "description": "Clear description of what to implement",
    "steps": "Step-by-step verification instructions",
    "passes": false,
    "retry_count": 0
  }}
]
```

Order tests from foundational features to advanced features.
Write the file to: {self.config.feature_list_path}
"""

    def select_next_task(self) -> TestTask | None:
        """Select the next failing test to work on.

        Returns:
            TestTask if a failing test found, None if all pass or all exhausted

        Note:
            Sets self.all_tests_exhausted = True if there are failing tests but
            all have reached max retries. This allows the caller to distinguish
            between "all pass" and "all exhausted" states.
        """
        feature_list_path = self.config.feature_list_path
        self.all_tests_exhausted = False  # Reset flag

        if not feature_list_path.exists():
            print("[WORKER] ⚠️ No feature_list.json found")
            return None

        try:
            with open(feature_list_path) as f:
                tests_data = json.load(f)

            # Track if we found any failing tests (even if exhausted)
            found_failing_tests = False
            exhausted_count = 0

            # Find first failing test (passes: false)
            for test_data in tests_data:
                if not test_data.get("passes", False):
                    found_failing_tests = True
                    task = TestTask.from_dict(test_data)

                    # Check retry limit
                    if task.retry_count >= self.config.max_retries_per_test:
                        print(f"[WORKER] ⏭️ Skipping {task.id} - max retries reached")
                        exhausted_count += 1
                        continue

                    self.assigned_task = task
                    print(f"[WORKER] 📌 Selected task: {task.id}")
                    print(f"[WORKER]    Description: {task.description}")
                    return task

            # Distinguish between "all pass" and "all failing tests exhausted"
            if found_failing_tests:
                # All failing tests have exhausted retries
                self.all_tests_exhausted = True
                print(f"[WORKER] ⚠️ All {exhausted_count} failing tests have exhausted retries")
                return None
            else:
                # All tests actually pass
                print("[WORKER] ✅ All tests pass - nothing to do")
                return None

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WORKER] ❌ Error reading feature_list.json: {e}")
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
- **Commands:** Bash (npm, git, node allowed)
- **Browser (Playwright MCP):**
  - `mcp__playwright__navigate` - Go to URL
  - `mcp__playwright__screenshot` - Capture page to file
  - `mcp__playwright__click` - Click element by selector
  - `mcp__playwright__fill` - Enter text in form field
  - `mcp__playwright__assert_visible` - Verify element visible

## Process

1. Understand the requirement from the description and steps
2. Implement the feature
3. Test with Playwright MCP:
   - `mcp__playwright__navigate` to the app URL (http://localhost:6174)
   - `mcp__playwright__screenshot` with path: `screenshots/issue-{self.config.issue_number}/{task.id}-<timestamp>.png`
   - **Check MCP output for console errors** - fix any errors before proceeding
   - Use `Read` tool to view the screenshot and verify visually
4. Fix any issues you find (console errors, visual problems)
5. Mark test as passing (set "passes": true) in feature_list.json using the Edit tool
6. Commit your changes with a descriptive message

## Console Error Detection

Playwright MCP includes console output in its response. After navigation:
- Review MCP output for `console.error` or `console.warn` messages
- Fix errors before marking test as passing

## Constraints

- Work ONLY on this test - do not touch other features
- Screenshot path MUST match: `screenshots/issue-{self.config.issue_number}/{task.id}-*.png`
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

        # Determine provider enum
        provider = Provider.BEDROCK if self.config.provider == "bedrock" else Provider.ANTHROPIC

        # Apply provider configuration
        if provider == Provider.BEDROCK:
            os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        apply_provider_config(provider)

        # Get API key based on provider
        if provider == Provider.ANTHROPIC:
            api_key = get_anthropic_api_key()
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
            elif not os.environ.get("ANTHROPIC_API_KEY"):
                print("[WORKER] ⚠️ Warning: ANTHROPIC_API_KEY not set - API calls may fail")
                print("[WORKER]    Set via environment variable or AWS Secrets Manager")
        else:
            # Bedrock provider - check for API key authentication
            # See: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
            bedrock_api_key = get_bedrock_api_key()
            if bedrock_api_key:
                os.environ[BEDROCK_API_KEY_ENV_VAR] = bedrock_api_key
                print("[WORKER] 🔑 Using Bedrock API key authentication")
            elif os.environ.get(BEDROCK_API_KEY_ENV_VAR):
                print("[WORKER] 🔑 Using Bedrock API key from environment")
            else:
                # No API key - will fall back to IAM credentials
                print("[WORKER] 🔐 Using IAM credentials for Bedrock authentication")

        # Get the correct model ID for the provider
        model_id = get_model_id("sonnet", provider)
        print(f"[WORKER] 🤖 Using model: {model_id} (provider: {provider.value})")

        # MCP servers - Playwright for browser automation
        mcp_servers = {
            "playwright": {
                "type": "stdio",
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
                model=model_id,
                system_prompt=system_prompt,
                mcp_servers=mcp_servers,
                allowed_tools=[
                    "Read", "Write", "Edit", "Glob", "Grep",
                    "Bash", "MultiEdit", "think",
                    "mcp__playwright__*",  # Playwright MCP tools
                ],
                hooks={
                    "PreToolUse": [
                        HookMatcher(matcher="*", hooks=[path_hook], timeout=120),  # 2 min for path validation
                    ],
                    "PostToolUse": [
                        HookMatcher(matcher="Bash", hooks=[bash_hook], timeout=90),  # 1.5 min for bash validation
                        HookMatcher(matcher="Read", hooks=[read_hook], timeout=30),  # 30 sec for read tracking
                    ],
                },
                max_turns=1000,  # Per-task limit
                cwd=project_root,
                setting_sources=["project"],  # Load CLAUDE.md project instructions
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
                print(f"[WORKER] ✅ Commit found: {result.stdout.decode().strip()}")
            else:
                print("[WORKER] ⚠️ No commit made in this session")

            return has_commit
        except Exception as e:
            print(f"[WORKER] ⚠️ Could not verify commit: {e}")
            return False

    def check_test_status(self) -> bool:
        """Check the status of the assigned test in feature_list.json.

        Returns:
            True if test passes, False otherwise
        """
        if not self.assigned_task:
            return False

        feature_list_path = self.config.feature_list_path

        try:
            with open(feature_list_path) as f:
                tests_data = json.load(f)

            for test in tests_data:
                if test.get("id") == self.assigned_task.id:
                    passes = test.get("passes", False)
                    print(f"[WORKER] 📊 Test {self.assigned_task.id} passes: {passes}")
                    return passes

            return False
        except Exception as e:
            print(f"[WORKER] ⚠️ Could not check test status: {e}")
            return False

    def increment_retry_count(self) -> None:
        """Increment retry count for the assigned test in feature_list.json."""
        if not self.assigned_task:
            return

        feature_list_path = self.config.feature_list_path

        try:
            with open(feature_list_path) as f:
                tests_data = json.load(f)

            for test in tests_data:
                if test.get("id") == self.assigned_task.id:
                    test["retry_count"] = test.get("retry_count", 0) + 1
                    break

            with open(feature_list_path, "w") as f:
                json.dump(tests_data, f, indent=2)

        except Exception as e:
            print(f"[WORKER] ⚠️ Could not update retry count: {e}")

    def determine_exit_status(self) -> WorkerStatus:
        """Determine the worker exit status based on test results.

        The harness (not the agent) decides when work is complete.

        Returns:
            WorkerStatus indicating what should happen next
        """
        # Check if assigned test passed
        test_passes = self.check_test_status()

        if not test_passes:
            # Test didn't pass - increment retry and continue
            self.increment_retry_count()

            if self.assigned_task and self.assigned_task.retry_count >= self.config.max_retries_per_test:
                print(f"[WORKER] ❌ Test {self.assigned_task.id} failed after {self.config.max_retries_per_test} attempts")
                return WorkerStatus.FAILED

            print("[WORKER] 🔄 Test not yet passing - will retry")
            return WorkerStatus.CONTINUE

        # Test passed - check if all tests pass
        feature_list_path = self.config.feature_list_path

        try:
            with open(feature_list_path) as f:
                tests_data = json.load(f)

            all_pass = all(t.get("passes", False) for t in tests_data)

            if all_pass:
                print("[WORKER] 🎉 ALL TESTS PASS - IMPLEMENTATION COMPLETE")
                return WorkerStatus.COMPLETE
            else:
                print("[WORKER] ✅ Test passed - more tests remain")
                return WorkerStatus.CONTINUE

        except Exception as e:
            print(f"[WORKER] ⚠️ Could not check all tests: {e}")
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
            print(f"[WORKER] ✅ Pushed to origin/{self.config.branch}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[WORKER] ❌ Push failed: {e}")
            return False
