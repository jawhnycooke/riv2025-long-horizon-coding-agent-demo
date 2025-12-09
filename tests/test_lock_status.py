"""Tests for the check_lock_status.py helper script."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch


# Add the scripts directory to the path
scripts_path = str(Path(__file__).parent.parent / ".github" / "scripts")
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)


# Create a proper mock for the github module with a real exception class
class MockGithubException(Exception):
    """Mock of github.GithubException for testing."""

    def __init__(self, status: int = 0, data: dict | None = None) -> None:
        self.status = status
        self.data = data or {}
        super().__init__(str(data))


# Create mock modules
mock_github = MagicMock()
mock_github.Github = MagicMock

mock_github_exception = ModuleType("github.GithubException")
mock_github_exception.GithubException = MockGithubException  # type: ignore[attr-defined]

sys.modules["github"] = mock_github
sys.modules["github.GithubException"] = mock_github_exception

from check_lock_status import format_duration, get_lock_status  # noqa: E402


class TestFormatDuration:
    """Tests for the format_duration helper function."""

    def test_format_seconds_only(self) -> None:
        """Test formatting durations less than a minute."""
        assert format_duration(0) == "0s"
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"

    def test_format_minutes_and_seconds(self) -> None:
        """Test formatting durations in minutes."""
        assert format_duration(60) == "1m 0s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3599) == "59m 59s"

    def test_format_hours_and_minutes(self) -> None:
        """Test formatting durations in hours."""
        assert format_duration(3600) == "1h 0m"
        assert format_duration(3660) == "1h 1m"
        assert format_duration(7200) == "2h 0m"
        assert format_duration(7380) == "2h 3m"


class TestGetLockStatus:
    """Tests for the get_lock_status function."""

    @patch("check_lock_status.Github")
    def test_no_lock_held(self, mock_github: MagicMock) -> None:
        """Test when no issue has the agent-building label."""
        mock_repo = MagicMock()
        mock_repo.get_issues.return_value = []
        mock_github.return_value.get_repo.return_value = mock_repo

        result = get_lock_status("owner/repo", "fake-token")

        assert result["locked"] is False
        assert result["issue_number"] is None
        assert result["lock_age_seconds"] == 0
        assert result["is_stale"] is False
        assert result["error"] is None

    @patch("check_lock_status.Github")
    def test_lock_held_not_stale(self, mock_github: MagicMock) -> None:
        """Test when an issue holds the lock and it's not stale."""
        # Create mock issue
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_issue.title = "Test Issue"

        # Create mock event for label addition (5 minutes ago)
        mock_event = MagicMock()
        mock_event.event = "labeled"
        mock_event.label = MagicMock()
        mock_event.label.name = "agent-building"
        mock_event.created_at = datetime.now(UTC) - timedelta(minutes=5)
        mock_issue.get_events.return_value = [mock_event]

        mock_repo = MagicMock()
        mock_repo.get_issues.return_value = [mock_issue]
        mock_github.return_value.get_repo.return_value = mock_repo

        result = get_lock_status("owner/repo", "fake-token", timeout_seconds=600)

        assert result["locked"] is True
        assert result["issue_number"] == 42
        assert result["issue_title"] == "Test Issue"
        assert 290 <= result["lock_age_seconds"] <= 310  # ~5 minutes with tolerance
        assert result["is_stale"] is False
        assert result["error"] is None

    @patch("check_lock_status.Github")
    def test_lock_held_is_stale(self, mock_github: MagicMock) -> None:
        """Test when an issue holds a stale lock."""
        # Create mock issue
        mock_issue = MagicMock()
        mock_issue.number = 99
        mock_issue.title = "Stale Issue"

        # Create mock event for label addition (15 minutes ago)
        mock_event = MagicMock()
        mock_event.event = "labeled"
        mock_event.label = MagicMock()
        mock_event.label.name = "agent-building"
        mock_event.created_at = datetime.now(UTC) - timedelta(minutes=15)
        mock_issue.get_events.return_value = [mock_event]

        mock_repo = MagicMock()
        mock_repo.get_issues.return_value = [mock_issue]
        mock_github.return_value.get_repo.return_value = mock_repo

        result = get_lock_status("owner/repo", "fake-token", timeout_seconds=600)

        assert result["locked"] is True
        assert result["issue_number"] == 99
        assert result["lock_age_seconds"] >= 890  # ~15 minutes
        assert result["is_stale"] is True
        assert result["error"] is None

    @patch("check_lock_status.Github")
    def test_github_api_error(self, mock_github: MagicMock) -> None:
        """Test handling of GitHub API errors."""
        # Create a GithubException-like error
        mock_github.return_value.get_repo.side_effect = MockGithubException(
            status=404, data={"message": "Not Found"}
        )

        result = get_lock_status("owner/repo", "fake-token")

        assert result["locked"] is False
        assert result["error"] is not None
        assert "Not Found" in result["error"]

    @patch("check_lock_status.Github")
    def test_no_label_events_found(self, mock_github: MagicMock) -> None:
        """Test when issue has label but no labeled event is found."""
        mock_issue = MagicMock()
        mock_issue.number = 123
        mock_issue.title = "No Events Issue"
        mock_issue.get_events.return_value = []  # No events

        mock_repo = MagicMock()
        mock_repo.get_issues.return_value = [mock_issue]
        mock_github.return_value.get_repo.return_value = mock_repo

        result = get_lock_status("owner/repo", "fake-token")

        assert result["locked"] is True
        assert result["issue_number"] == 123
        # Without events, lock age should remain at default
        assert result["lock_age_seconds"] == 0
        assert result["is_stale"] is False

    @patch("check_lock_status.Github")
    def test_custom_timeout(self, mock_github: MagicMock) -> None:
        """Test with custom timeout value."""
        mock_issue = MagicMock()
        mock_issue.number = 1
        mock_issue.title = "Custom Timeout"

        # 3 minutes ago
        mock_event = MagicMock()
        mock_event.event = "labeled"
        mock_event.label = MagicMock()
        mock_event.label.name = "agent-building"
        mock_event.created_at = datetime.now(UTC) - timedelta(minutes=3)
        mock_issue.get_events.return_value = [mock_event]

        mock_repo = MagicMock()
        mock_repo.get_issues.return_value = [mock_issue]
        mock_github.return_value.get_repo.return_value = mock_repo

        # With 2 minute timeout, the 3-minute-old lock should be stale
        result = get_lock_status("owner/repo", "fake-token", timeout_seconds=120)

        assert result["locked"] is True
        assert result["is_stale"] is True
        assert result["timeout_seconds"] == 120

        # With 5 minute timeout, the 3-minute-old lock should not be stale
        result = get_lock_status("owner/repo", "fake-token", timeout_seconds=300)

        assert result["locked"] is True
        assert result["is_stale"] is False
        assert result["timeout_seconds"] == 300
