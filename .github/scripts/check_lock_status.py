#!/usr/bin/env python3
"""
Lock Status Checker for Agent Builder Workflow

This script checks the status of the agent-building lock across issues.
It can be used for debugging, monitoring, and runbook procedures.

Usage:
    python check_lock_status.py --repo owner/repo

Output:
    JSON with lock status information including:
    - locked: Whether any issue holds the lock
    - issue_number: Issue holding the lock (if any)
    - lock_age_seconds: How long the lock has been held
    - is_stale: Whether the lock exceeds the timeout threshold

Environment:
    GITHUB_TOKEN: GitHub personal access token with issues:read permission
    LOCK_TIMEOUT_SECONDS: Lock timeout in seconds (default: 600)
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime


try:
    from github import Github
    from github.GithubException import GithubException

    _HAS_GITHUB = True
except ImportError:
    _HAS_GITHUB = False
    Github = None  # type: ignore[misc, assignment]
    GithubException = Exception  # type: ignore[misc, assignment]


def get_lock_status(
    repo_name: str,
    github_token: str,
    timeout_seconds: int = 600,
) -> dict:
    """
    Check the current lock status for the agent-building label.

    Args:
        repo_name: Repository in "owner/repo" format
        github_token: GitHub personal access token
        timeout_seconds: Lock timeout threshold in seconds

    Returns:
        Dictionary with lock status information
    """
    result = {
        "locked": False,
        "issue_number": None,
        "issue_title": None,
        "lock_age_seconds": 0,
        "is_stale": False,
        "timeout_seconds": timeout_seconds,
        "error": None,
    }

    try:
        gh = Github(github_token)
        repo = gh.get_repo(repo_name)

        # Find issues with agent-building label
        building_issues = list(repo.get_issues(state="open", labels=["agent-building"]))

        if not building_issues:
            return result

        # Get the first (should be only) issue with the label
        issue = building_issues[0]
        result["locked"] = True
        result["issue_number"] = issue.number
        result["issue_title"] = issue.title

        # Find when the label was added
        label_added_at: datetime | None = None
        for event in issue.get_events():
            if event.event == "labeled" and event.label.name == "agent-building":
                label_added_at = event.created_at

        if label_added_at:
            now = datetime.now(UTC)
            # Ensure label_added_at is timezone-aware
            if label_added_at.tzinfo is None:
                label_added_at = label_added_at.replace(tzinfo=UTC)
            lock_age = (now - label_added_at).total_seconds()
            result["lock_age_seconds"] = int(lock_age)
            result["is_stale"] = lock_age > timeout_seconds
            result["label_added_at"] = label_added_at.isoformat()

    except GithubException as e:
        result["error"] = f"GitHub API error: {e.data.get('message', str(e))}"
    except Exception as e:
        result["error"] = f"Unexpected error: {e!s}"

    return result


def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def main() -> None:
    """Main entry point."""
    if not _HAS_GITHUB:
        print("Error: PyGithub is required. Install with: pip install PyGithub")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Check agent-building lock status")
    parser.add_argument(
        "--repo",
        required=True,
        help="Repository in owner/repo format",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("LOCK_TIMEOUT_SECONDS", "600")),
        help="Lock timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON",
    )

    args = parser.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    status = get_lock_status(args.repo, github_token, args.timeout)

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        # Human-readable output
        if status["error"]:
            print(f"❌ Error: {status['error']}")
            sys.exit(1)

        if not status["locked"]:
            print("🔓 No lock held - agent-building label not found on any open issue")
        else:
            lock_emoji = "⚠️" if status["is_stale"] else "🔒"
            stale_indicator = " (STALE)" if status["is_stale"] else ""

            print(f"{lock_emoji} Lock Status{stale_indicator}")
            print(f"   Issue: #{status['issue_number']} - {status['issue_title']}")
            print(f"   Lock age: {format_duration(status['lock_age_seconds'])}")
            print(f"   Timeout: {format_duration(status['timeout_seconds'])}")

            if status["is_stale"]:
                print()
                print("   ⚠️  This lock is stale and should be released!")
                print(
                    "   Run: gh issue edit {} --remove-label agent-building".format(
                        status["issue_number"]
                    )
                )

    sys.exit(0 if not status["error"] else 1)


if __name__ == "__main__":
    main()
