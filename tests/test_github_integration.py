"""Tests for src/github_integration.py - GitHub issue management."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import src.github_integration as github_integration_module
from src.github_integration import (
    LABEL_BUILDING,
    LABEL_COMPLETE,
    BuildableIssue,
    GitHubIssueManager,
)


class TestBuildableIssue:
    """Tests for BuildableIssue dataclass."""

    def test_to_dict(self) -> None:
        """BuildableIssue converts to dict correctly."""
        created = datetime(2025, 1, 1, 12, 0, 0)
        issue = BuildableIssue(
            number=42,
            title="Test Issue",
            body="Issue body",
            labels=["feature", "priority-high"],
            thumbs_up_count=5,
            has_staff_approval=True,
            approved_by=["staff1", "staff2"],
            created_at=created,
        )

        result = issue.to_dict()

        assert result["number"] == 42
        assert result["title"] == "Test Issue"
        assert result["body"] == "Issue body"
        assert result["labels"] == ["feature", "priority-high"]
        assert result["votes"] == 5
        assert result["approved"] is True
        assert result["approved_by"] == ["staff1", "staff2"]
        assert result["created"] == "2025-01-01T12:00:00"


class TestLabelFiltering:
    """Tests for label filtering in get_buildable_issues."""

    @pytest.fixture(autouse=True)
    def setup_authorized_approvers(self) -> None:
        """Set up authorized approvers for all tests in this class."""
        # Patch the module-level AUTHORIZED_APPROVERS set
        self._original_approvers = github_integration_module.AUTHORIZED_APPROVERS
        github_integration_module.AUTHORIZED_APPROVERS = {"authorized-user"}
        yield
        github_integration_module.AUTHORIZED_APPROVERS = self._original_approvers

    @pytest.fixture
    def mock_github_manager(self) -> GitHubIssueManager:
        """Create a GitHubIssueManager with mocked GitHub client."""
        with patch("src.github_integration.Github") as mock_github:
            mock_repo = MagicMock()
            mock_github.return_value.get_repo.return_value = mock_repo
            manager = GitHubIssueManager("test/repo", "fake-token")
            return manager

    def _create_mock_issue(
        self,
        number: int,
        title: str,
        labels: list[str],
        has_approval: bool = True,
        is_building: bool = False,
        is_complete: bool = False,
    ) -> MagicMock:
        """Create a mock GitHub issue."""
        mock_issue = MagicMock()
        mock_issue.number = number
        mock_issue.title = title
        mock_issue.body = f"Body for {title}"
        mock_issue.created_at = datetime(2025, 1, 1, 12, 0, 0)

        # Create mock labels
        mock_labels = []
        for label_name in labels:
            mock_label = MagicMock()
            mock_label.name = label_name
            mock_labels.append(mock_label)

        # Add building/complete labels if needed
        if is_building:
            building_label = MagicMock()
            building_label.name = LABEL_BUILDING
            mock_labels.append(building_label)
        if is_complete:
            complete_label = MagicMock()
            complete_label.name = LABEL_COMPLETE
            mock_labels.append(complete_label)

        mock_issue.labels = mock_labels

        # Mock reactions for approval
        if has_approval:
            mock_reaction = MagicMock()
            mock_reaction.content = "rocket"
            mock_reaction.user.login = "authorized-user"
            mock_issue.get_reactions.return_value = [mock_reaction]
        else:
            mock_issue.get_reactions.return_value = []

        return mock_issue

    def test_no_label_filter_returns_all_approved(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Without label filter, all approved issues are returned."""
        issues = [
            self._create_mock_issue(1, "Issue 1", ["feature"]),
            self._create_mock_issue(2, "Issue 2", ["bug"]),
            self._create_mock_issue(3, "Issue 3", ["feature", "priority-high"]),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues()

        assert len(result) == 3
        assert {r.number for r in result} == {1, 2, 3}

    def test_single_label_filter(self, mock_github_manager: GitHubIssueManager) -> None:
        """Filter by single label only returns matching issues."""
        issues = [
            self._create_mock_issue(1, "Feature Issue", ["feature"]),
            self._create_mock_issue(2, "Bug Issue", ["bug"]),
            self._create_mock_issue(3, "Another Feature", ["feature", "priority"]),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues(required_labels=["feature"])

        assert len(result) == 2
        assert {r.number for r in result} == {1, 3}

    def test_multiple_labels_filter_requires_all(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Multiple labels filter requires issue to have ALL labels."""
        issues = [
            self._create_mock_issue(1, "Feature Only", ["feature"]),
            self._create_mock_issue(2, "Priority Only", ["priority-high"]),
            self._create_mock_issue(3, "Both Labels", ["feature", "priority-high"]),
            self._create_mock_issue(
                4, "All Three", ["feature", "priority-high", "enhancement"]
            ),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues(
            required_labels=["feature", "priority-high"]
        )

        assert len(result) == 2
        assert {r.number for r in result} == {3, 4}

    def test_label_filter_case_insensitive(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Label matching is case-insensitive."""
        issues = [
            self._create_mock_issue(1, "Upper Case", ["FEATURE"]),
            self._create_mock_issue(2, "Lower Case", ["feature"]),
            self._create_mock_issue(3, "Mixed Case", ["Feature"]),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues(required_labels=["feature"])

        assert len(result) == 3

    def test_label_filter_with_whitespace(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Label filter handles whitespace in input."""
        issues = [
            self._create_mock_issue(1, "Feature Issue", ["feature", "bug"]),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        # Labels with extra whitespace - should still match
        result = mock_github_manager.get_buildable_issues(
            required_labels=["  feature  ", "  bug  "]
        )

        assert len(result) == 1
        assert result[0].number == 1

    def test_empty_label_list_same_as_none(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Empty label list behaves same as no filter."""
        issues = [
            self._create_mock_issue(1, "Issue 1", ["feature"]),
            self._create_mock_issue(2, "Issue 2", ["bug"]),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result_none = mock_github_manager.get_buildable_issues(required_labels=None)
        result_empty = mock_github_manager.get_buildable_issues(required_labels=[])

        assert len(result_none) == len(result_empty) == 2

    def test_label_filter_excludes_building_issues(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Building issues excluded even with matching labels."""
        issues = [
            self._create_mock_issue(1, "Feature", ["feature"]),
            self._create_mock_issue(2, "Building", ["feature"], is_building=True),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues(required_labels=["feature"])

        assert len(result) == 1
        assert result[0].number == 1

    def test_label_filter_excludes_complete_issues(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Complete issues excluded even with matching labels."""
        issues = [
            self._create_mock_issue(1, "Feature", ["feature"]),
            self._create_mock_issue(2, "Complete", ["feature"], is_complete=True),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues(required_labels=["feature"])

        assert len(result) == 1
        assert result[0].number == 1

    def test_no_matching_labels_returns_empty(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Returns empty list when no issues match labels."""
        issues = [
            self._create_mock_issue(1, "Feature", ["feature"]),
            self._create_mock_issue(2, "Bug", ["bug"]),
        ]
        mock_github_manager.repo.get_issues.return_value = issues

        result = mock_github_manager.get_buildable_issues(
            required_labels=["nonexistent-label"]
        )

        assert len(result) == 0


class TestGetNextBuildableIssue:
    """Tests for get_next_buildable_issue with label filtering."""

    @pytest.fixture(autouse=True)
    def setup_authorized_approvers(self) -> None:
        """Set up authorized approvers for all tests in this class."""
        self._original_approvers = github_integration_module.AUTHORIZED_APPROVERS
        github_integration_module.AUTHORIZED_APPROVERS = {"authorized-user"}
        yield
        github_integration_module.AUTHORIZED_APPROVERS = self._original_approvers

    @pytest.fixture
    def mock_github_manager(self) -> GitHubIssueManager:
        """Create a GitHubIssueManager with mocked GitHub client."""
        with patch("src.github_integration.Github") as mock_github:
            mock_repo = MagicMock()
            mock_github.return_value.get_repo.return_value = mock_repo
            manager = GitHubIssueManager("test/repo", "fake-token")
            return manager

    def test_passes_labels_to_get_buildable_issues(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """get_next_buildable_issue passes labels to get_buildable_issues."""
        with patch.object(
            mock_github_manager, "get_buildable_issues"
        ) as mock_get_buildable:
            mock_get_buildable.return_value = []

            mock_github_manager.get_next_buildable_issue(
                required_labels=["feature", "priority"]
            )

            mock_get_buildable.assert_called_once_with(
                required_labels=["feature", "priority"]
            )

    def test_returns_none_when_no_matching_issues(
        self, mock_github_manager: GitHubIssueManager
    ) -> None:
        """Returns None when no issues match label filter."""
        with patch.object(
            mock_github_manager, "get_buildable_issues"
        ) as mock_get_buildable:
            mock_get_buildable.return_value = []

            result = mock_github_manager.get_next_buildable_issue(
                required_labels=["nonexistent"]
            )

            assert result is None
