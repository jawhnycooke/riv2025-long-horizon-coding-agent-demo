"""Worker configuration for the harness-enforced architecture.

This module provides configuration dataclasses for the worker container,
separating configuration from execution logic.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class WorkerStatus(Enum):
    """Exit status for worker sessions."""

    CONTINUE = 0      # Test passed, more tests remain - run another session
    COMPLETE = 1      # All tests pass - implementation complete
    FAILED = 2        # Unrecoverable error - stop trying
    BROKEN_STATE = 3  # Smoke test failed - broken state detected


@dataclass
class WorkerConfig:
    """Configuration for worker harness.

    Attributes:
        issue_number: GitHub issue number being worked on
        github_repo: GitHub repository (owner/repo format)
        branch: Git branch for agent work (default: agent-runtime)
        provider: Claude provider (anthropic or bedrock)
        environment: Environment name for metrics
        max_retries_per_test: Maximum attempts per failing test
        smoke_test_timeout: Timeout for smoke tests in seconds
        dev_server_url: URL for the development server
        dev_server_port: Port for the development server
        workspace_dir: Base directory for workspace
        screenshots_dir: Directory for test screenshots
    """

    issue_number: int
    github_repo: str
    branch: str = "agent-runtime"
    provider: str = "anthropic"
    environment: str = "reinvent"
    max_retries_per_test: int = 3
    smoke_test_timeout: int = 30
    dev_server_url: str = "http://localhost"
    dev_server_port: int = 6174
    workspace_dir: Path = field(default_factory=lambda: Path("/app/workspace"))
    screenshots_dir: str = "screenshots"

    @property
    def dev_server_address(self) -> str:
        """Full dev server address."""
        return f"{self.dev_server_url}:{self.dev_server_port}"

    @property
    def repo_dir(self) -> Path:
        """Directory where repository is cloned."""
        return self.workspace_dir / self.github_repo.replace("/", "_")

    @property
    def feature_list_path(self) -> Path:
        """Path to feature_list.json file."""
        return self.repo_dir / "feature_list.json"

    @property
    def progress_file_path(self) -> Path:
        """Path to claude-progress.txt file."""
        return self.repo_dir / "claude-progress.txt"

    @property
    def init_script_path(self) -> Path:
        """Path to init.sh script."""
        return self.repo_dir / "init.sh"

    @classmethod
    def from_environment(cls) -> "WorkerConfig":
        """Create config from environment variables.

        Environment Variables:
            ISSUE_NUMBER: GitHub issue number (required)
            GITHUB_REPOSITORY: GitHub repo in owner/repo format (required)
            AGENT_BRANCH: Git branch (default: agent-runtime)
            PROVIDER: anthropic or bedrock (default: anthropic)
            ENVIRONMENT: Environment name (default: reinvent)
            MAX_RETRIES_PER_TEST: Max retries per test (default: 3)
            SMOKE_TEST_TIMEOUT: Smoke test timeout seconds (default: 30)
            DEV_SERVER_PORT: Development server port (default: 6174)
            WORKSPACE_DIR: Base workspace directory (default: /app/workspace)

        Returns:
            WorkerConfig instance

        Raises:
            ValueError: If required environment variables are missing
        """
        issue_number = os.environ.get("ISSUE_NUMBER")
        if not issue_number:
            raise ValueError("ISSUE_NUMBER environment variable is required")

        github_repo = os.environ.get("GITHUB_REPOSITORY")
        if not github_repo:
            raise ValueError("GITHUB_REPOSITORY environment variable is required")

        workspace = os.environ.get("WORKSPACE_DIR", "/app/workspace")
        # Use current directory if /app doesn't exist (local dev)
        if not Path("/app").exists():
            workspace = str(Path.cwd() / "workspace")

        return cls(
            issue_number=int(issue_number),
            github_repo=github_repo,
            branch=os.environ.get("AGENT_BRANCH", "agent-runtime"),
            provider=os.environ.get("PROVIDER", "anthropic").lower(),
            environment=os.environ.get("ENVIRONMENT", "reinvent"),
            max_retries_per_test=int(os.environ.get("MAX_RETRIES_PER_TEST", "3")),
            smoke_test_timeout=int(os.environ.get("SMOKE_TEST_TIMEOUT", "30")),
            dev_server_port=int(os.environ.get("DEV_SERVER_PORT", "6174")),
            workspace_dir=Path(workspace),
        )


@dataclass
class TestTask:
    """A single test task assigned to the agent.

    Attributes:
        id: Unique test identifier
        description: Human-readable test description
        steps: Steps to verify the test passes
        passes: Whether the test is passing (Anthropic-style boolean)
        retry_count: Number of times this test has been attempted
    """

    id: str
    description: str
    steps: str
    passes: bool = False
    retry_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "TestTask":
        """Create TestTask from dictionary (feature_list.json format)."""
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            steps=data.get("steps", ""),
            passes=data.get("passes", False),
            retry_count=data.get("retry_count", 0),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "description": self.description,
            "steps": self.steps,
            "passes": self.passes,
            "retry_count": self.retry_count,
        }
