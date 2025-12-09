"""Tests for src/security.py - Security validation hooks and utilities."""

from pathlib import Path

import pytest

from src.config import ALLOWED_BASH_COMMANDS
from src.security import (
    SecurityValidator,
    _deny_response,
    _extract_test_id,
    clear_screenshot_tracking,
    track_screenshot_read,
    was_screenshot_viewed,
)


class TestScreenshotTracking:
    """Tests for screenshot tracking functionality."""

    def setup_method(self) -> None:
        """Clear screenshot tracking before each test."""
        clear_screenshot_tracking()

    def test_track_screenshot_png(self) -> None:
        """Track PNG screenshot view."""
        path = "/project/screenshots/issue-1/test-1-screenshot.png"
        track_screenshot_read(path)
        assert was_screenshot_viewed(path)

    def test_track_console_log(self) -> None:
        """Track console log view."""
        path = "/project/screenshots/issue-1/test-1-console.txt"
        track_screenshot_read(path)
        assert was_screenshot_viewed(path)

    def test_ignore_non_screenshot_file(self) -> None:
        """Don't track non-screenshot files."""
        path = "/project/src/main.py"
        track_screenshot_read(path)
        assert not was_screenshot_viewed(path)

    def test_ignore_file_not_in_screenshots_dir(self) -> None:
        """Don't track files outside screenshots directory."""
        path = "/project/other/file.png"
        track_screenshot_read(path)
        assert not was_screenshot_viewed(path)

    def test_clear_tracking(self) -> None:
        """Clear screenshot tracking state."""
        path = "/project/screenshots/issue-1/test.png"
        track_screenshot_read(path)
        assert was_screenshot_viewed(path)

        clear_screenshot_tracking()
        assert not was_screenshot_viewed(path)


class TestExtractTestId:
    """Tests for _extract_test_id function."""

    def test_extract_id_from_id_field(self) -> None:
        """Extract test ID from "id" field."""
        old_string = '{"id": "test-navigation", "name": "Test"}'
        result = _extract_test_id(old_string, "")
        assert result == "test-navigation"

    def test_extract_id_from_name_field(self) -> None:
        """Extract and slugify test ID from "name" field."""
        old_string = '{"name": "First Time User Flow"}'
        result = _extract_test_id(old_string, "")
        assert result == "first-time-user-flow"

    def test_prefer_id_over_name(self) -> None:
        """Prefer explicit id over name field."""
        old_string = '{"id": "explicit-id", "name": "Different Name"}'
        result = _extract_test_id(old_string, "")
        assert result == "explicit-id"

    def test_no_id_found(self) -> None:
        """Return None when no ID can be extracted."""
        old_string = '{"other": "value"}'
        result = _extract_test_id(old_string, "")
        assert result is None


class TestDenyResponse:
    """Tests for _deny_response helper."""

    def test_deny_response_structure(self) -> None:
        """Deny response has correct structure."""
        result = _deny_response("Test reason")

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "Test reason"


class TestPathValidation:
    """Tests for path validation in SecurityValidator."""

    def test_path_within_project_root(self, project_root: Path) -> None:
        """Accept paths within project root."""
        file_path = str(project_root / "src" / "main.py")
        is_valid, error = SecurityValidator._validate_path_within_run_directory(
            file_path, str(project_root)
        )
        assert is_valid
        assert error == ""

    def test_path_outside_project_root(self, project_root: Path) -> None:
        """Reject paths outside project root."""
        file_path = "/etc/passwd"
        is_valid, error = SecurityValidator._validate_path_within_run_directory(
            file_path, str(project_root)
        )
        assert not is_valid
        assert "outside the allowed project directory" in error

    def test_path_with_traversal(self, project_root: Path) -> None:
        """Reject paths with traversal attempts."""
        file_path = str(project_root / ".." / "secret.txt")
        is_valid, _error = SecurityValidator._validate_path_within_run_directory(
            file_path, str(project_root)
        )
        assert not is_valid

    def test_no_project_root_fails(self) -> None:
        """Reject when no project root is set."""
        is_valid, error = SecurityValidator._validate_path_within_run_directory(
            "/some/path", None
        )
        assert not is_valid
        assert "No project root" in error


class TestBashSecurityHook:
    """Tests for bash_security_hook."""

    @pytest.mark.asyncio
    async def test_allowed_command(self) -> None:
        """Allow commands in the allowed list."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert result == {}  # Empty means allowed

    @pytest.mark.asyncio
    async def test_blocked_command(self) -> None:
        """Block commands not in allowed list."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "sudo rm -rf /"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "not allowed" in result["hookSpecificOutput"]["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_non_bash_tool_passthrough(self) -> None:
        """Non-Bash tools pass through."""
        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/some/file"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert result == {}

    @pytest.mark.asyncio
    async def test_rm_without_allowed_pattern_blocked(self) -> None:
        """Block rm commands not in allowed patterns."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /important"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_rm_node_modules_allowed(self) -> None:
        """Allow rm -rf node_modules."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf node_modules"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert result == {}

    @pytest.mark.asyncio
    async def test_git_init_blocked(self) -> None:
        """Block git init command."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "git init"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "git init" in result["hookSpecificOutput"]["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_git_add_allowed(self) -> None:
        """Allow git add command."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "git add ."},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert result == {}

    @pytest.mark.asyncio
    async def test_sed_bulk_test_modification_blocked(self) -> None:
        """Block sed commands that modify tests.json passes field."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "sed -i 's/false/true/g' tests.json"},
        }
        result = await SecurityValidator.bash_security_hook(input_data)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestPathSecurityInBash:
    """Tests for path validation within bash commands."""

    @pytest.mark.asyncio
    async def test_bash_with_safe_path(self, project_root: Path) -> None:
        """Allow bash commands with paths inside project root."""
        # Create a file to reference
        test_file = project_root / "test.txt"
        test_file.touch()

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": f"cat {test_file}"},
        }
        result = await SecurityValidator.bash_security_hook(
            input_data, project_root=str(project_root)
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_bash_with_unsafe_path(self, project_root: Path) -> None:
        """Block bash commands with paths outside project root."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "cat /etc/passwd"},
        }
        result = await SecurityValidator.bash_security_hook(
            input_data, project_root=str(project_root)
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestUniversalPathSecurityHook:
    """Tests for universal_path_security_hook."""

    @pytest.mark.asyncio
    async def test_read_tool_inside_project(self, project_root: Path) -> None:
        """Allow Read tool for files inside project."""
        test_file = project_root / "src" / "main.py"
        test_file.parent.mkdir(exist_ok=True)
        test_file.touch()

        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": str(test_file)},
        }
        result = await SecurityValidator.universal_path_security_hook(
            input_data, project_root=str(project_root)
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_read_tool_outside_project(self, project_root: Path) -> None:
        """Block Read tool for files outside project."""
        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/passwd"},
        }
        result = await SecurityValidator.universal_path_security_hook(
            input_data, project_root=str(project_root)
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_bash_delegates_to_bash_hook(self, project_root: Path) -> None:
        """Bash commands are handled by bash_security_hook."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }
        result = await SecurityValidator.universal_path_security_hook(
            input_data, project_root=str(project_root)
        )
        assert result == {}  # ls is allowed


class TestAllowedCommands:
    """Tests for allowed bash commands configuration."""

    def test_essential_commands_allowed(self) -> None:
        """Essential commands are in allowed list."""
        essential = ["npm", "npx", "git", "ls", "cat", "echo", "mkdir", "cp"]
        for cmd in essential:
            assert cmd in ALLOWED_BASH_COMMANDS, f"{cmd} should be allowed"

    def test_dangerous_commands_not_allowed(self) -> None:
        """Dangerous commands are not in allowed list."""
        dangerous = ["sudo", "su", "passwd", "useradd", "chroot", "mount"]
        for cmd in dangerous:
            assert cmd not in ALLOWED_BASH_COMMANDS, f"{cmd} should not be allowed"
