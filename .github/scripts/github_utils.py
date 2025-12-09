#!/usr/bin/env python3
"""F020: Shared GitHub utilities for workflow scripts.

This module provides common utilities used across GitHub Actions workflows:
- Session ID extraction from issue comments
- Issue label management
- Reaction checking
- Input sanitization

Usage in workflows:
    import sys
    sys.path.insert(0, '.github/scripts')
    from github_utils import extract_session_ids, check_issue_approval
"""

import os
import re
from typing import Any

# Constants
ROCKET_EMOJI = "rocket"
LABEL_BUILDING = "agent-building"
LABEL_COMPLETE = "agent-complete"
LABEL_FAILED = "tests-failed"


def extract_session_ids(comments: list[Any]) -> list[str]:
    """Extract all unique session IDs from issue comments.

    Looks for session IDs in two common formats:
    1. Session ID: `xxx`
    2. | **Session ID** | `xxx` |

    Args:
        comments: List of GitHub comment objects with .body attribute

    Returns:
        List of unique session ID strings found in comments
    """
    session_ids: set[str] = set()

    # Pattern 1: Session ID: `xxx`
    pattern1 = r"Session ID:\s*`([^`]+)`"

    # Pattern 2: | **Session ID** | `xxx` |
    pattern2 = r"\|\s*\*\*Session ID\*\*\s*\|\s*`([^`]+)`\s*\|"

    for comment in comments:
        body = getattr(comment, "body", "") or ""
        session_ids.update(re.findall(pattern1, body))
        session_ids.update(re.findall(pattern2, body))

    return list(session_ids)


def check_issue_approval(
    issue: Any, authorized_approvers: set[str], required_labels: list[str] | None = None
) -> tuple[bool, str | None, int]:
    """Check if an issue has been approved for building.

    Args:
        issue: GitHub issue object
        authorized_approvers: Set of usernames who can approve with rocket emoji
        required_labels: Optional list of labels that must ALL be present

    Returns:
        Tuple of (is_approved, approver_username, vote_count)
    """
    # Get issue labels
    labels = [label.name for label in issue.labels]
    labels_lower = [label.lower() for label in labels]

    # Skip if already complete
    if LABEL_COMPLETE in labels:
        return False, None, 0

    # Check required labels if specified
    if required_labels:
        required_lower = [label.lower() for label in required_labels]
        if not all(req in labels_lower for req in required_lower):
            return False, None, 0

    # Cache reactions to avoid duplicate API calls
    reactions = list(issue.get_reactions())
    approver = None
    vote_count = 0

    for reaction in reactions:
        if reaction.content == ROCKET_EMOJI:
            if reaction.user.login in authorized_approvers:
                approver = reaction.user.login
                break

    # Count +1 votes
    vote_count = sum(1 for r in reactions if r.content == "+1")

    return approver is not None, approver, vote_count


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input for safe use in shell commands and markdown.

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length (truncates if exceeded)

    Returns:
        Sanitized text string
    """
    if not text:
        return ""

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "..."

    # Remove null bytes and other control characters (except newline, tab)
    text = "".join(char for char in text if char == "\n" or char == "\t" or (ord(char) >= 32))

    return text


def write_github_output(key: str, value: str) -> None:
    """Write a key-value pair to GitHub Actions output.

    Args:
        key: Output variable name
        value: Output value
    """
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a") as f:
            # Handle multiline values with heredoc syntax
            if "\n" in value:
                import uuid

                delimiter = f"ghadelimiter_{uuid.uuid4().hex}"
                f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                f.write(f"{key}={value}\n")


def write_job_summary(content: str) -> None:
    """Write content to GitHub Actions job summary.

    Args:
        content: Markdown content to write to job summary
    """
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")


def format_issue_table(issues: list[dict[str, Any]]) -> str:
    """Format a list of issues as a markdown table.

    Args:
        issues: List of issue dicts with 'number', 'title', 'votes' keys

    Returns:
        Markdown table string
    """
    if not issues:
        return "*No issues found*"

    lines = [
        "| # | Title | Votes |",
        "|---|-------|-------|",
    ]

    for issue in issues:
        title = sanitize_input(issue.get("title", ""), max_length=50)
        lines.append(f"| #{issue['number']} | {title} | {issue.get('votes', 0)} |")

    return "\n".join(lines)
