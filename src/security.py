"""Security utilities for Claude Code."""

import glob
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import get_audit_logger
from .config import (
    ALLOWED_BASH_COMMANDS,
    ALLOWED_NODE_PATTERNS,
    ALLOWED_PKILL_PATTERNS,
    ALLOWED_RM_COMMANDS,
    BLOCKED_SED_PATTERNS,
    BLOCKED_TESTS_JSON_PATTERNS,
)
from .error_messages import SecurityErrorMessages


# ============================================================================
# Screenshot Verification State (with persistence)
# ============================================================================
# Track which screenshots have been viewed (read) during the session.
# This prevents the agent from marking tests as passing without actually
# viewing the screenshot evidence.
#
# F025: State is now persisted to JSON file for session continuity.
# Stale screenshots (>24h) are filtered out on load.

_viewed_screenshots: set[str] = set()
_verification_state_file: str | None = None
_STALE_THRESHOLD_HOURS = 24


def _get_verification_state_path(project_root: str) -> Path | None:
    """Get path to verification state file.

    Args:
        project_root: Project root directory

    Returns:
        Path to .verification-state.json, or None if not determinable
    """
    issue_number = os.environ.get("ISSUE_NUMBER")
    if not issue_number or not project_root:
        return None
    return Path(project_root) / "screenshots" / f"issue-{issue_number}" / ".verification-state.json"


def _load_verification_state(state_path: Path) -> dict[str, Any]:
    """Load verification state from JSON file.

    Args:
        state_path: Path to state file

    Returns:
        State dict with viewed_screenshots list and timestamps
    """
    if not state_path.exists():
        return {"viewed_screenshots": {}}

    try:
        with open(state_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ Failed to load verification state: {e}")
        return {"viewed_screenshots": {}}


def _save_verification_state(state_path: Path, viewed: set[str]) -> None:
    """Save verification state to JSON file.

    Args:
        state_path: Path to state file
        viewed: Set of viewed screenshot paths
    """
    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Create state dict with timestamps
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "last_updated": now,
        "viewed_screenshots": {
            path: now for path in viewed
        }
    }

    try:
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"⚠️ Failed to save verification state: {e}")


def _filter_stale_screenshots(viewed_dict: dict[str, str]) -> set[str]:
    """Filter out screenshots viewed more than 24 hours ago.

    Args:
        viewed_dict: Dict mapping path -> ISO timestamp

    Returns:
        Set of non-stale screenshot paths
    """
    now = datetime.now(timezone.utc)
    result = set()

    for path, timestamp_str in viewed_dict.items():
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            age_hours = (now - timestamp).total_seconds() / 3600
            if age_hours < _STALE_THRESHOLD_HOURS:
                result.add(path)
            else:
                print(f"📸 Filtered stale screenshot (>{_STALE_THRESHOLD_HOURS}h): {path}")
        except (ValueError, TypeError):
            # Invalid timestamp, skip this entry
            pass

    return result


def initialize_screenshot_tracking(project_root: str | None) -> None:
    """Initialize screenshot tracking, loading persisted state if available.

    Call this at session start to restore verification state from previous sessions.

    Args:
        project_root: Project root directory
    """
    global _viewed_screenshots, _verification_state_file

    if not project_root:
        return

    state_path = _get_verification_state_path(project_root)
    if state_path:
        _verification_state_file = str(state_path)
        state = _load_verification_state(state_path)
        viewed_dict = state.get("viewed_screenshots", {})
        _viewed_screenshots = _filter_stale_screenshots(viewed_dict)

        if _viewed_screenshots:
            print(f"📸 Restored {len(_viewed_screenshots)} viewed screenshot(s) from previous session")


def track_screenshot_read(file_path: str, project_root: str | None = None) -> None:
    """Track that a screenshot or console log was viewed by the agent.

    Args:
        file_path: Path to the screenshot/console file that was read
        project_root: Project root directory for persistence (optional)
    """
    global _verification_state_file

    if "screenshots/" in file_path:
        if file_path.endswith(".png") or file_path.endswith("-console.txt"):
            _viewed_screenshots.add(file_path)
            file_type = "screenshot" if file_path.endswith(".png") else "console log"
            print(f"📸 Tracked {file_type} view: {file_path}")

            # F025: Persist state after each track operation
            if _verification_state_file:
                _save_verification_state(Path(_verification_state_file), _viewed_screenshots)
            elif project_root:
                state_path = _get_verification_state_path(project_root)
                if state_path:
                    _verification_state_file = str(state_path)
                    _save_verification_state(state_path, _viewed_screenshots)


def was_screenshot_viewed(file_path: str) -> bool:
    """Check if a specific screenshot was viewed.

    Args:
        file_path: Path to check

    Returns:
        True if the screenshot was previously read by the agent
    """
    return file_path in _viewed_screenshots


def clear_screenshot_tracking() -> None:
    """Clear the screenshot tracking state (for testing/reset)."""
    _viewed_screenshots.clear()


def _extract_test_id(old_string: str, new_string: str) -> str | None:
    """Extract test ID from the edit context.

    Looks for patterns like:
    - "id": "test-name"
    - "name": "Test Name" (converted to slug)

    Args:
        old_string: The original string being replaced
        new_string: The new string replacing it

    Returns:
        Test ID if found, None otherwise
    """
    # Combine old and new strings for context
    context = old_string + new_string

    # Try to find "id": "xxx" pattern
    id_match = re.search(r'"id"\s*:\s*"([^"]+)"', context)
    if id_match:
        return id_match.group(1)

    # Try to find "name": "xxx" and slugify it
    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', context)
    if name_match:
        name = name_match.group(1)
        # Convert to slug: "First Time User" -> "first-time-user"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
        return slug

    return None


def _deny_response(reason: str) -> dict[str, Any]:
    """Create a deny response for PreToolUse hooks.

    Args:
        reason: Explanation of why the action was denied

    Returns:
        Hook response dict with deny decision
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


class SecurityValidator:
    """Validates bash commands and file paths for security."""

    @staticmethod
    def _validate_path_within_run_directory(
        file_path: str, project_root: str | None, tool_name: str = "operation"
    ) -> tuple[bool, str]:
        """Validate that a path is within the run-specific directory.

        Args:
            file_path: Path to validate
            project_root: Project root directory (run-specific directory)
            tool_name: Name of the tool requesting validation (for error messages)

        Returns:
            Tuple of (is_valid, error_reason)
        """
        if not project_root:
            return False, SecurityErrorMessages.no_project_root()

        try:
            # Resolve absolute paths to handle relative paths and symlinks
            project_root_resolved = Path(project_root).resolve()
            file_path_resolved = Path(file_path).resolve()

            # Check if the file path is within the project root
            try:
                file_path_resolved.relative_to(project_root_resolved)
                return True, ""
            except ValueError:
                # Path is outside project root
                return (
                    False,
                    SecurityErrorMessages.path_outside_project(
                        file_path, project_root, tool_name
                    ),
                )

        except (OSError, RuntimeError) as e:
            return False, f"Error validating path: {e}"

    @staticmethod
    def _validate_bash_paths(command: str, project_root: str) -> dict[str, Any] | None:
        """Validate paths in bash commands to ensure they stay within the run directory.

        Args:
            command: Bash command to validate
            project_root: Project root directory

        Returns:
            Hook response dict if path is invalid, None if valid
        """
        import shlex

        try:
            # Parse command into tokens
            tokens = shlex.split(command)
        except ValueError:
            # If command can't be parsed, allow bash to handle the error
            return None

        if not tokens:
            return None

        # Commands that commonly take file paths as arguments
        path_sensitive_commands = {
            "cat",
            "less",
            "more",
            "head",
            "tail",
            "file",
            "stat",
            "cp",
            "mv",
            "rm",
            "mkdir",
            "rmdir",
            "touch",
            "chmod",
            "chown",
            "ls",
            "find",
            "locate",
            "grep",
            "egrep",
            "fgrep",
            "vi",
            "vim",
            "nano",
            "emacs",
            "gedit",
            "git",
            "python",
            "python3",
            "node",
            "npm",
            "pip",
            "tar",
            "unzip",
            "zip",
            "gzip",
            "gunzip",
            "curl",
            "wget",
            "scp",
            "rsync",
        }

        first_word = tokens[0].lower()

        # Check if this is a command that might operate on files outside our directory
        if first_word not in path_sensitive_commands:
            return None

        # Extract potential file paths from the command
        # Look for arguments that look like paths (start with /, ./, ../, or contain /)
        potential_paths = []

        for token in tokens[1:]:  # Skip the command itself
            # Skip flags and options (start with -)
            if token.startswith("-"):
                continue

            # Check if token looks like a path
            if (
                "/" in token
                or token.startswith("./")
                or token.startswith("../")
                or token.startswith("~/")
                or token.startswith("/")
                or
                # Also check for common file patterns
                ("." in token and len(token.split(".")) <= 3)
            ):  # Basic file extension check
                potential_paths.append(token)

        # Validate each potential path
        for path in potential_paths:
            # Skip URLs and special cases
            if any(
                pattern in path
                for pattern in [
                    "http://",
                    "https://",
                    "ftp://",
                    "|",
                    ">",
                    "<",
                    "&&",
                    "||",
                    "/dev/null",  # Allow /dev/null for redirection
                ]
            ):
                continue

            # For relative paths, resolve them relative to current directory (which should be project root)
            is_valid, error_reason = (
                SecurityValidator._validate_path_within_run_directory(
                    path, project_root
                )
            )

            if not is_valid:
                print(f"🚨 BLOCKED Bash command: {error_reason}")
                print(f"   Command: {command}")
                # Audit log blocked path access
                get_audit_logger().log_bash_command(
                    command,
                    blocked=True,
                    reason=f"Restricted path: {error_reason}",
                )
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Bash command contains restricted path: {error_reason}",
                    }
                }

        return None

    @staticmethod
    async def bash_security_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any | None = None,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Security hook to restrict Bash commands to only allowed ones.

        Args:
            input_data: Tool input data
            tool_use_id: Tool use ID (optional)
            context: Hook context (optional)
            project_root: Project root directory (optional)

        Returns:
            Hook response dict
        """
        # Validate input structure
        if not input_data or not isinstance(input_data, dict):
            return {}

        tool_name = input_data.get("tool_name")
        if tool_name != "Bash":
            return {}

        tool_input = input_data.get("tool_input")
        if not tool_input or not isinstance(tool_input, dict):
            return {}

        command = tool_input.get("command", "")
        if not command or not isinstance(command, str):
            return {}

        # Get first word of command
        first_word = command.strip().split()[0] if command.strip() else ""

        # Validate paths in the command for certain operations
        if project_root:
            path_validation_result = SecurityValidator._validate_bash_paths(
                command, project_root
            )
            if path_validation_result:
                return path_validation_result

        # Special check for rm command
        if first_word == "rm":
            return SecurityValidator._validate_rm_command(command)

        # Special check for node command
        if first_word == "node":
            return SecurityValidator._validate_node_command(command)

        # Special check for pkill command
        if first_word == "pkill":
            return SecurityValidator._validate_pkill_command(command)

        # Special check for sed command - block bulk test result modifications
        if first_word == "sed":
            sed_result = SecurityValidator._validate_sed_command(command)
            if sed_result:  # Non-empty means blocked
                return sed_result
            # If not blocked, fall through to general allow check

        # Block any bash command that could modify tests.json (awk, jq, python, node, etc.)
        tests_json_result = SecurityValidator._validate_tests_json_bash_command(command)
        if tests_json_result:  # Non-empty means blocked
            return tests_json_result

        # Block git init - creates nested repos that break commit tracking
        if first_word == "git":
            tokens = command.strip().split()
            if len(tokens) >= 2 and tokens[1] == "init":
                error_msg = SecurityErrorMessages.git_init_blocked()
                print("🚨 BLOCKED: git init - use the existing repository")
                get_audit_logger().log_bash_command(
                    command, blocked=True, reason="git init not allowed"
                )
                return _deny_response(error_msg)

        # Check if command is in allowed list
        if first_word in ALLOWED_BASH_COMMANDS:
            print(f"✅ Allowed: {first_word}")
            # Audit log allowed command (exit code will be updated post-execution)
            get_audit_logger().log_bash_command(command, blocked=False)
            return {}
        else:
            error_msg = SecurityErrorMessages.command_not_allowed(
                command, first_word, list(ALLOWED_BASH_COMMANDS)
            )
            print(f"🚨 BLOCKED: {command}")
            # Audit log blocked command
            get_audit_logger().log_bash_command(
                command,
                blocked=True,
                reason=f"Command '{first_word}' not in allowed list",
            )
            return _deny_response(error_msg)

    @staticmethod
    async def universal_path_security_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any | None = None,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Universal security hook to restrict all operations to the run-specific directory.

        Args:
            input_data: Tool input data
            tool_use_id: Tool use ID (optional)
            context: Hook context (optional)
            project_root: Project root directory (run-specific directory)

        Returns:
            Hook response dict
        """
        # Validate input structure
        if not input_data or not isinstance(input_data, dict):
            return {}

        tool_name = input_data.get("tool_name")
        if not tool_name or not isinstance(tool_name, str):
            return {}

        tool_input = input_data.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}

        # Handle Bash commands (includes both command restriction and path validation)
        if tool_name == "Bash":
            return await SecurityValidator.bash_security_hook(
                input_data, tool_use_id, context, project_root
            )

        # File operation tools to validate
        file_tools = ["Read", "Edit", "Write", "MultiEdit", "Glob", "Grep"]

        if tool_name not in file_tools:
            return {}

        # Extract file path based on tool type
        file_path = None
        if tool_name in ["Read", "Edit", "Write", "MultiEdit"]:
            file_path = tool_input.get("file_path")
        elif tool_name == "Glob":
            # For Glob, validate the base path
            file_path = tool_input.get("path", ".")
        elif tool_name == "Grep":
            # For Grep, validate the search path
            file_path = tool_input.get("path", ".")

        if not file_path:
            error_msg = SecurityErrorMessages.no_file_path(tool_name)
            return _deny_response(error_msg)

        # Validate path
        is_valid, error_reason = SecurityValidator._validate_path_within_run_directory(
            file_path, project_root
        )

        if not is_valid:
            print(f"🚨 BLOCKED {tool_name}: {error_reason}")
            # Audit log blocked file operation
            operation = "read" if tool_name == "Read" else "write"
            if tool_name == "Edit":
                operation = "edit"
            get_audit_logger().log_file_operation(
                operation, file_path, blocked=True, reason=error_reason
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": error_reason,
                }
            }

        # Additional validation for Edit/Write operations on tests.json
        if tool_name in ["Edit", "Write", "MultiEdit"]:
            test_validation_result = (
                SecurityValidator._validate_test_result_modification(
                    tool_input, project_root
                )
            )
            if test_validation_result:
                # Audit log blocked test modification
                get_audit_logger().log_file_operation(
                    "edit",
                    file_path,
                    blocked=True,
                    reason="Test result modification blocked",
                )
                return test_validation_result

        # Audit log allowed file operation
        operation = "read" if tool_name == "Read" else "write"
        if tool_name == "Edit":
            operation = "edit"
        get_audit_logger().log_file_operation(operation, file_path, blocked=False)

        print(f"✅ Allowed {tool_name}: {file_path}")
        return {}

    @staticmethod
    def _validate_rm_command(command: str) -> dict[str, Any]:
        """Validate rm command against allowed patterns.

        Args:
            command: Command to validate

        Returns:
            Hook response dict
        """
        if command.strip() in ALLOWED_RM_COMMANDS:
            print(f"✅ Allowed: {command} (cleaning node_modules)")
            get_audit_logger().log_bash_command(command, blocked=False)
            return {}
        else:
            error_msg = SecurityErrorMessages.rm_not_allowed(command)
            print(f"🚨 BLOCKED: {command}")
            get_audit_logger().log_bash_command(
                command,
                blocked=True,
                reason="rm only allowed for 'rm -rf node_modules'",
            )
            return _deny_response(error_msg)

    @staticmethod
    def _validate_node_command(command: str) -> dict[str, Any]:
        """Validate node command against allowed patterns.

        Args:
            command: Command to validate

        Returns:
            Hook response dict
        """
        if any(pattern in command for pattern in ALLOWED_NODE_PATTERNS):
            print(f"✅ Allowed: {command}")
            get_audit_logger().log_bash_command(command, blocked=False)
            return {}
        else:
            error_msg = SecurityErrorMessages.node_not_allowed(command)
            print(f"🚨 BLOCKED: {command}")
            get_audit_logger().log_bash_command(
                command, blocked=True, reason="Node only allowed for server.js"
            )
            return _deny_response(error_msg)

    @staticmethod
    def _validate_pkill_command(command: str) -> dict[str, Any]:
        """Validate pkill command against allowed patterns.

        Args:
            command: Command to validate

        Returns:
            Hook response dict
        """
        if command.strip() in ALLOWED_PKILL_PATTERNS:
            print(f"✅ Allowed: {command}")
            get_audit_logger().log_bash_command(command, blocked=False)
            return {}
        else:
            error_msg = SecurityErrorMessages.pkill_not_allowed(
                command, list(ALLOWED_PKILL_PATTERNS)
            )
            print(f"🚨 BLOCKED: {command}")
            get_audit_logger().log_bash_command(
                command, blocked=True, reason="pkill not in allowed patterns"
            )
            return _deny_response(error_msg)

    @staticmethod
    def _validate_sed_command(command: str) -> dict[str, Any]:
        """Validate sed command against blocked patterns.

        Prevents bulk modification of test results in tests.json.
        The agent must update test results individually after verification,
        not use sed to mass-update all tests as passing.

        Args:
            command: Command to validate

        Returns:
            Hook response dict (empty if allowed, deny response if blocked)
        """
        for pattern in BLOCKED_SED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                error_msg = SecurityErrorMessages.sed_tests_json_blocked(command)
                print(f"🚨 BLOCKED: {command}")
                get_audit_logger().log_bash_command(
                    command, blocked=True, reason="sed bulk-modify tests.json blocked"
                )
                return _deny_response(error_msg)
        # sed command is allowed (doesn't match blocked patterns)
        return {}

    @staticmethod
    async def cd_enforcement_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any | None = None,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """PostToolUse hook to enforce directory boundaries after cd commands.

        Args:
            input_data: Tool input data
            tool_use_id: Tool use ID (optional)
            context: Hook context (optional)
            project_root: Project root directory

        Returns:
            Hook response dict
        """

        tool_name = input_data.get("tool_name", "")

        if tool_name == "Bash":
            tool_input = input_data.get("tool_input", {})
            command = tool_input.get("command", "")

            # Only check after cd commands
            if command.strip().startswith("cd ") and project_root:
                # Get the actual current directory
                current_dir = os.getcwd()

                # Check if we've escaped the project root
                if not current_dir.startswith(project_root):
                    print("⚠️ Directory escape detected!")
                    print(f"   Current dir: {current_dir}")
                    print(f"   Project root: {project_root}")
                    print("   Resetting to project root...")

                    # Reset to project root
                    os.chdir(project_root)

                    return {
                        "systemMessage": f"⚠️ You navigated outside the project directory. I've automatically returned you to the project root at `{project_root}`. Please stay within the project directory."
                    }

        return {}

    @staticmethod
    def _validate_tests_json_bash_command(command: str) -> dict[str, Any]:
        """Block bash commands that could modify tests.json.

        Prevents use of awk, jq, python, node, echo, etc. to modify tests.json.
        The agent must use the Edit tool with screenshot verification.

        Args:
            command: Bash command to validate

        Returns:
            Hook response dict (empty if allowed, deny response if blocked)
        """
        for pattern in BLOCKED_TESTS_JSON_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                error_msg = SecurityErrorMessages.bash_tests_json_blocked(command)
                print(f"🚨 BLOCKED: {command}")
                get_audit_logger().log_bash_command(
                    command, blocked=True, reason="bash modify tests.json blocked"
                )
                return _deny_response(error_msg)
        return {}

    @staticmethod
    def _validate_test_result_modification(
        tool_input: dict[str, Any],
        project_root: str | None,
    ) -> dict[str, Any] | None:
        """Validate that screenshot exists and was viewed before marking test as passing.

        This prevents the agent from claiming tests pass without actually running
        and verifying them. The agent must:
        1. Execute the test steps
        2. Take a screenshot with the test ID in the filename
           (path: screenshots/issue-{issue_number}/{test_id}-*.png)
        3. View the screenshot using the Read tool
        4. Check MCP output for console errors (shown in Playwright MCP response)
        5. Only then can they mark the test as passing

        Note: Console log files are optional. With Playwright MCP, console errors
        are visible in the MCP tool output, so separate console.txt files are not
        required.

        Args:
            tool_input: Tool input data containing file_path, old_string, new_string
            project_root: Project root directory

        Returns:
            Hook response dict if validation fails, None if allowed
        """
        file_path = tool_input.get("file_path", "")

        # Only check tests.json modifications
        if not file_path.endswith("tests.json"):
            return None

        # Parse the edit to find which test is being marked as passing
        new_string = tool_input.get("new_string", "")
        old_string = tool_input.get("old_string", "")

        # If changing "passes": false to "passes": true, require screenshot
        if '"passes": true' not in new_string and "'passes': true" not in new_string:
            return None  # Not marking as passing, allow

        # Extract test ID from context
        test_id = _extract_test_id(old_string, new_string)

        if not test_id:
            error_msg = SecurityErrorMessages.test_no_id_found()
            print("🚨 BLOCKED: Cannot determine test ID from edit context")
            return _deny_response(error_msg)

        # Get issue number from environment
        issue_number = os.environ.get("ISSUE_NUMBER", "0")

        # Check if project_root is set
        if not project_root:
            print("⚠️ WARNING: No project_root set, cannot validate screenshots")
            return None  # Can't validate without project root

        # =====================================================================
        # Check 1: Screenshot must exist
        # =====================================================================
        screenshot_pattern = (
            f"{project_root}/screenshots/issue-{issue_number}/{test_id}-*.png"
        )
        screenshots = glob.glob(screenshot_pattern)

        if not screenshots:
            error_msg = SecurityErrorMessages.test_no_screenshot(
                test_id, issue_number, screenshot_pattern
            )
            print(f"🚨 BLOCKED: No screenshot found for test '{test_id}'")
            print(f"   Pattern: {screenshot_pattern}")
            return _deny_response(error_msg)

        # =====================================================================
        # Check 2: Screenshot must have been viewed
        # =====================================================================
        screenshot_viewed = any(was_screenshot_viewed(s) for s in screenshots)
        if not screenshot_viewed:
            error_msg = SecurityErrorMessages.test_screenshot_not_viewed(
                test_id, screenshots[0]
            )
            print(f"🚨 BLOCKED: Screenshot exists for test '{test_id}' but not viewed")
            return _deny_response(error_msg)

        # =====================================================================
        # Console Log Check (Optional - MCP shows console in output)
        # =====================================================================
        # With Playwright MCP, console errors are visible in the MCP tool output.
        # Console log files are no longer required but checked if present.
        console_pattern = (
            f"{project_root}/screenshots/issue-{issue_number}/{test_id}-console.txt"
        )
        console_files = glob.glob(console_pattern)

        if console_files:
            # Console log exists - verify it was viewed
            console_viewed = any(was_screenshot_viewed(f) for f in console_files)
            if not console_viewed:
                print(f"⚠️ Console log exists for test '{test_id}' but not viewed")
                print(f"   Consider viewing: {console_files[0]}")
            else:
                print(f"✅ Console log for '{test_id}' was viewed")
        else:
            # No console log file - that's OK with MCP (console shown in tool output)
            print(f"ℹ️ No console log file for '{test_id}' (MCP shows console in output)")

        print(
            f"✅ Test '{test_id}' verified: screenshot exists and was viewed"
        )
        return None  # Allow the edit

    @staticmethod
    async def track_read_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any | None = None,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """PostToolUse hook to track when screenshots are read.

        This is called after the Read tool completes. It tracks which
        screenshot files have been viewed by the agent.

        Args:
            input_data: Tool input data
            tool_use_id: Tool use ID (optional)
            context: Hook context (optional)
            project_root: Project root directory (optional)

        Returns:
            Empty dict (just tracks state, no output)
        """
        # Validate input structure
        if not input_data or not isinstance(input_data, dict):
            return {}

        tool_name = input_data.get("tool_name")
        if tool_name != "Read":
            return {}

        tool_input = input_data.get("tool_input")
        if not tool_input or not isinstance(tool_input, dict):
            return {}

        file_path = tool_input.get("file_path", "")
        if file_path and isinstance(file_path, str):
            # F025: Pass project_root for persistence
            track_screenshot_read(file_path, project_root)

        return {}
