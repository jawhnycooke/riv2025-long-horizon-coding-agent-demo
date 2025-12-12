"""Tests for the SecurityErrorMessages class (F011)."""

import pytest

from src.error_messages import SecurityErrorMessages


class TestPathErrorMessages:
    """Tests for path-related error messages."""

    def test_path_outside_project_basic(self) -> None:
        """Test basic path outside project error message."""
        msg = SecurityErrorMessages.path_outside_project(
            "/etc/passwd", "/home/user/project"
        )
        assert "🚫 PATH BLOCKED" in msg
        assert "/etc/passwd" in msg
        assert "/home/user/project" in msg
        assert "How to fix" in msg

    def test_path_outside_project_with_tool_name(self) -> None:
        """Test path error with custom tool name."""
        msg = SecurityErrorMessages.path_outside_project(
            "/etc/passwd", "/home/user/project", tool_name="Read"
        )
        assert "Read denied" in msg

    def test_no_project_root_message(self) -> None:
        """Test error when no project root is set."""
        msg = SecurityErrorMessages.no_project_root()
        assert "🚫 PATH BLOCKED" in msg
        assert "No project root" in msg
        assert "How to fix" in msg

    def test_no_file_path_message(self) -> None:
        """Test error when no file path is provided."""
        msg = SecurityErrorMessages.no_file_path("Edit")
        assert "🚫 PATH BLOCKED" in msg
        assert "No file path provided" in msg
        assert "Edit" in msg


class TestCommandErrorMessages:
    """Tests for command-related error messages."""

    def test_command_not_allowed_basic(self) -> None:
        """Test basic command not allowed error."""
        msg = SecurityErrorMessages.command_not_allowed(
            "sudo rm -rf /", "sudo", ["npm", "git", "ls"]
        )
        assert "🚫 COMMAND BLOCKED" in msg
        assert "'sudo' not allowed" in msg
        assert "sudo" in msg
        assert "How to fix" in msg
        # Should suggest that sudo is not allowed for security
        assert "root/sudo" in msg.lower()

    def test_command_not_allowed_curl_suggestion(self) -> None:
        """Test curl command gets WebFetch suggestion."""
        msg = SecurityErrorMessages.command_not_allowed(
            "curl https://example.com", "curl", ["npm", "git"]
        )
        assert "WebFetch" in msg

    def test_command_not_allowed_vim_suggestion(self) -> None:
        """Test vim command gets Edit tool suggestion."""
        msg = SecurityErrorMessages.command_not_allowed(
            "vim file.txt", "vim", ["npm", "git"]
        )
        assert "Edit" in msg or "Write" in msg

    def test_rm_not_allowed_message(self) -> None:
        """Test rm command error message."""
        msg = SecurityErrorMessages.rm_not_allowed("rm -rf /important")
        assert "🚫 COMMAND BLOCKED" in msg
        assert "rm command restricted" in msg
        assert "rm -rf node_modules" in msg
        assert "How to fix" in msg

    def test_node_not_allowed_message(self) -> None:
        """Test node command error message."""
        msg = SecurityErrorMessages.node_not_allowed("node malicious.js")
        assert "🚫 COMMAND BLOCKED" in msg
        assert "node command restricted" in msg
        assert "server.js" in msg
        assert "npm run" in msg

    def test_pkill_not_allowed_message(self) -> None:
        """Test pkill command error message."""
        allowed = ["pkill -f 'npm run dev'", "pkill -f 'node server'"]
        msg = SecurityErrorMessages.pkill_not_allowed("pkill -9 python", allowed)
        assert "🚫 COMMAND BLOCKED" in msg
        assert "pkill command restricted" in msg
        assert "npm run dev" in msg

    def test_git_init_blocked_message(self) -> None:
        """Test git init error message."""
        msg = SecurityErrorMessages.git_init_blocked()
        assert "🚫 COMMAND BLOCKED" in msg
        assert "git init not allowed" in msg
        assert "git add" in msg
        assert "git commit" in msg


class TestFeatureListErrorMessages:
    """Tests for feature_list.json modification error messages."""

    def test_sed_feature_list_blocked(self) -> None:
        """Test sed command on feature_list.json error."""
        msg = SecurityErrorMessages.sed_feature_list_blocked(
            "sed -i 's/false/true/g' feature_list.json"
        )
        assert "🚫 COMMAND BLOCKED" in msg
        assert "sed" in msg
        assert "feature_list.json" in msg
        assert "screenshot" in msg.lower()

    def test_bash_feature_list_blocked(self) -> None:
        """Test bash command on feature_list.json error."""
        msg = SecurityErrorMessages.bash_feature_list_blocked(
            "jq '.features[].passes = true' feature_list.json"
        )
        assert "🚫 COMMAND BLOCKED" in msg
        assert "bash" in msg.lower() or "jq" in msg.lower()
        assert "Edit tool" in msg


class TestTestVerificationErrorMessages:
    """Tests for test verification error messages."""

    def test_no_screenshot_message(self) -> None:
        """Test error when no screenshot exists."""
        msg = SecurityErrorMessages.test_no_screenshot(
            "login-flow", "42", "screenshots/issue-42/login-flow-*.png"
        )
        assert "🚫 TEST BLOCKED" in msg
        assert "No screenshot found" in msg
        assert "login-flow" in msg
        assert "issue-42" in msg
        assert "mcp__playwright__screenshot" in msg or "mcp__playwright__navigate" in msg

    def test_screenshot_not_viewed_message(self) -> None:
        """Test error when screenshot exists but wasn't viewed."""
        msg = SecurityErrorMessages.test_screenshot_not_viewed(
            "login-flow", "screenshots/issue-42/login-flow-12345.png"
        )
        assert "🚫 TEST BLOCKED" in msg
        assert "Screenshot not verified" in msg
        assert "Read tool" in msg
        assert "screenshots/issue-42/login-flow-12345.png" in msg

    def test_no_console_log_message(self) -> None:
        """Test info message when no console log exists (optional with MCP)."""
        msg = SecurityErrorMessages.test_no_console_log(
            "login-flow", "42", "screenshots/issue-42/login-flow-console.txt"
        )
        # Console logs are now optional with MCP - shows info, not blocked
        assert "ℹ️" in msg or "No console log" in msg
        assert "login-flow" in msg
        assert "MCP" in msg or "optional" in msg.lower()

    def test_console_not_viewed_message(self) -> None:
        """Test warning when console log exists but wasn't viewed (optional with MCP)."""
        msg = SecurityErrorMessages.test_console_not_viewed(
            "login-flow", "screenshots/issue-42/login-flow-console.txt"
        )
        # Console logs are now optional with MCP - shows warning, not blocked
        assert "⚠️" in msg or "wasn't viewed" in msg
        assert "login-flow" in msg
        assert "MCP" in msg or "console" in msg.lower()

    def test_no_id_found_message(self) -> None:
        """Test error when test ID cannot be determined."""
        msg = SecurityErrorMessages.test_no_id_found()
        assert "🚫 TEST BLOCKED" in msg
        assert "Cannot determine test ID" in msg
        assert "'id'" in msg or "'name'" in msg


class TestMessageFormatConsistency:
    """Tests to ensure all messages follow consistent format."""

    @pytest.fixture
    def blocking_error_messages(self) -> list[str]:
        """Get all blocking error messages (🚫) for consistency testing."""
        return [
            SecurityErrorMessages.path_outside_project("/a", "/b"),
            SecurityErrorMessages.no_project_root(),
            SecurityErrorMessages.no_file_path("Read"),
            SecurityErrorMessages.command_not_allowed("cmd", "cmd", ["npm"]),
            SecurityErrorMessages.rm_not_allowed("rm -rf /"),
            SecurityErrorMessages.node_not_allowed("node bad.js"),
            SecurityErrorMessages.pkill_not_allowed("pkill x", ["pkill -f npm"]),
            SecurityErrorMessages.git_init_blocked(),
            SecurityErrorMessages.sed_feature_list_blocked("sed x"),
            SecurityErrorMessages.bash_feature_list_blocked("jq x"),
            SecurityErrorMessages.test_no_screenshot("test", "1", "pattern"),
            SecurityErrorMessages.test_screenshot_not_viewed("test", "path"),
            SecurityErrorMessages.test_no_id_found(),
        ]

    @pytest.fixture
    def info_warning_messages(self) -> list[str]:
        """Get info/warning messages (ℹ️/⚠️) - console logs are optional with MCP."""
        return [
            SecurityErrorMessages.test_no_console_log("test", "1", "pattern"),
            SecurityErrorMessages.test_console_not_viewed("test", "path"),
        ]

    def test_blocking_messages_start_with_block_emoji(
        self, blocking_error_messages: list[str]
    ) -> None:
        """Blocking messages should start with 🚫."""
        for msg in blocking_error_messages:
            assert msg.startswith("🚫"), f"Message doesn't start with 🚫: {msg[:50]}"

    def test_blocking_messages_have_how_to_fix(
        self, blocking_error_messages: list[str]
    ) -> None:
        """Blocking messages should include fix suggestions."""
        for msg in blocking_error_messages:
            assert "How to fix" in msg, f"Message missing fix suggestions: {msg[:50]}"

    def test_info_warning_messages_have_appropriate_emoji(
        self, info_warning_messages: list[str]
    ) -> None:
        """Info/warning messages should start with ℹ️ or ⚠️."""
        for msg in info_warning_messages:
            assert msg.startswith("ℹ️") or msg.startswith("⚠️"), (
                f"Message doesn't start with info/warning emoji: {msg[:50]}"
            )
