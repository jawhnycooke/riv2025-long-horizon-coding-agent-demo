"""Claude Code utilities package."""

from .cloudwatch_metrics import MetricsPublisher
from .config import *
from .git_manager import GitHubConfig, GitManager
from .github_integration import (
    BuildableIssue,
    GitHubIssueManager,
    claim_issue_label,
    get_approved_issues_simple,
    post_comment,
    release_issue_label,
)
from .logging_utils import LoggingManager
from .prompt_templates import PromptTemplater
from .secrets import (
    cleanup_token_file,
    get_anthropic_api_key,
    get_github_token,
    get_secret,
    read_github_token_from_file,
    write_github_token_to_file,
)
from .security import SecurityValidator
from .session_manager import SessionManager
from .token_tracker import SessionTotals, TokenTracker, TokenUsage


__version__ = "1.0.0"
__all__ = [
    "BuildableIssue",
    "GitHubConfig",
    "GitHubIssueManager",
    "GitManager",
    "LoggingManager",
    "MetricsPublisher",
    "PromptTemplater",
    "SecurityValidator",
    "SessionManager",
    "SessionTotals",
    "TokenTracker",
    "TokenUsage",
    # GitHub integration helpers
    "claim_issue_label",
    "get_approved_issues_simple",
    "post_comment",
    "release_issue_label",
    # Secrets helpers
    "cleanup_token_file",
    "get_anthropic_api_key",
    "get_github_token",
    "get_secret",
    "read_github_token_from_file",
    "write_github_token_to_file",
]
