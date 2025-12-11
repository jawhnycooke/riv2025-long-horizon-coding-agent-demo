#!/usr/bin/env python3
"""Orchestrator container entrypoint for two-container ECS architecture.

This orchestrator uses Claude Agent SDK to intelligently manage the issue-to-build
workflow. It monitors GitHub for approved issues, claims them, and delegates
the actual building work to Worker containers via AWS Step Functions.

Architecture:
    Orchestrator (this file) → Step Functions → Worker Container (claude_code_agent.py)

Responsibilities:
    - Poll GitHub for issues approved with 🚀 reaction
    - Claim issues by adding agent-building label
    - Invoke Step Functions to start worker builds
    - Monitor worker progress via Step Functions execution status
    - Post updates to GitHub issues
    - Publish CloudWatch heartbeat metrics

Environment Variables:
    GITHUB_REPOSITORY: Target repo (e.g., "owner/repo")
    GITHUB_TOKEN: GitHub PAT (from Secrets Manager)
    ANTHROPIC_API_KEY: For Claude Agent SDK (from Secrets Manager)
    STATE_MACHINE_ARN: Step Functions state machine ARN
    PROVIDER: "anthropic" or "bedrock"
    AUTHORIZED_APPROVERS: Comma-separated GitHub usernames who can approve
    ENVIRONMENT: Environment name for CloudWatch metrics
    POLL_INTERVAL_SECONDS: How often to poll for new issues (default: 300)
"""

import json
import os
import time
from datetime import UTC, datetime

import boto3

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, tool

from src import (
    MetricsPublisher,
    claim_issue_label,
    get_anthropic_api_key,
    get_approved_issues_simple,
    get_github_token,
    post_comment,
    release_issue_label,
)
from src.config import Provider, apply_provider_config

# Configuration from environment
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
PROVIDER = os.environ.get("PROVIDER", "anthropic").lower()
ENVIRONMENT = os.environ.get("ENVIRONMENT", "reinvent")

# Authorized approvers (can approve with 🚀)
_approvers_env = os.environ.get("AUTHORIZED_APPROVERS", "")
AUTHORIZED_APPROVERS = set(a.strip() for a in _approvers_env.split(",") if a.strip())


# =============================================================================
# Claude Agent SDK Tools
# =============================================================================


@tool
def get_approved_issues() -> list[dict]:
    """Get all GitHub issues that have been approved with 🚀 reaction.

    Returns a list of issues sorted by votes (highest first), then by
    creation date (oldest first).

    Returns:
        List of approved issues with number, title, body, votes, and labels.
    """
    github_token = get_github_token(GITHUB_REPO)
    if not github_token:
        return {"error": "Failed to get GitHub token"}

    issues = get_approved_issues_simple(
        github_repo=GITHUB_REPO,
        github_token=github_token,
        authorized_approvers=AUTHORIZED_APPROVERS,
    )
    return issues


@tool
def claim_issue(issue_number: int) -> dict:
    """Claim a GitHub issue by adding the agent-building label.

    This prevents other orchestrator instances from picking up the same issue.

    Args:
        issue_number: The GitHub issue number to claim.

    Returns:
        Success or error status.
    """
    github_token = get_github_token(GITHUB_REPO)
    if not github_token:
        return {"error": "Failed to get GitHub token"}

    success = claim_issue_label(
        github_repo=GITHUB_REPO,
        github_token=github_token,
        issue_number=issue_number,
    )
    return {"success": success, "issue_number": issue_number}


@tool
def release_issue(issue_number: int, mark_complete: bool = False) -> dict:
    """Release a GitHub issue by removing the agent-building label.

    Optionally marks the issue as complete by adding agent-complete label.

    Args:
        issue_number: The GitHub issue number to release.
        mark_complete: Whether to add agent-complete label.

    Returns:
        Success or error status.
    """
    github_token = get_github_token(GITHUB_REPO)
    if not github_token:
        return {"error": "Failed to get GitHub token"}

    success = release_issue_label(
        github_repo=GITHUB_REPO,
        github_token=github_token,
        issue_number=issue_number,
        add_complete_label=mark_complete,
    )
    return {"success": success, "issue_number": issue_number}


@tool
def start_worker_build(issue_number: int) -> dict:
    """Start a worker container to build the specified GitHub issue.

    This invokes the Step Functions state machine which will run the worker
    container via ECS RunTask.

    Args:
        issue_number: The GitHub issue number to build.

    Returns:
        Execution ARN if successful, error otherwise.
    """
    if not STATE_MACHINE_ARN:
        return {"error": "STATE_MACHINE_ARN not configured"}

    try:
        sfn = boto3.client("stepfunctions")
        response = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=f"issue-{issue_number}-{int(time.time())}",
            input=json.dumps({
                "issue_number": issue_number,
                "github_repo": GITHUB_REPO,
                "provider": PROVIDER,
                "environment": ENVIRONMENT,
            }),
        )
        print(f"✅ Started worker build for issue #{issue_number}")
        return {
            "success": True,
            "execution_arn": response["executionArn"],
            "issue_number": issue_number,
        }
    except Exception as e:
        print(f"❌ Failed to start worker build: {e}")
        return {"error": str(e), "issue_number": issue_number}


@tool
def check_worker_status(execution_arn: str) -> dict:
    """Check the status of a worker build.

    Args:
        execution_arn: The Step Functions execution ARN.

    Returns:
        Status information including RUNNING, SUCCEEDED, FAILED, etc.
    """
    try:
        sfn = boto3.client("stepfunctions")
        response = sfn.describe_execution(executionArn=execution_arn)
        return {
            "status": response["status"],
            "start_date": response["startDate"].isoformat(),
            "stop_date": response.get("stopDate", "").isoformat() if response.get("stopDate") else None,
            "execution_arn": execution_arn,
        }
    except Exception as e:
        return {"error": str(e), "execution_arn": execution_arn}


@tool
def post_issue_comment(issue_number: int, comment: str) -> dict:
    """Post a comment to a GitHub issue.

    Args:
        issue_number: The GitHub issue number.
        comment: The markdown comment to post.

    Returns:
        Success or error status.
    """
    github_token = get_github_token(GITHUB_REPO)
    if not github_token:
        return {"error": "Failed to get GitHub token"}

    success = post_comment(
        github_repo=GITHUB_REPO,
        github_token=github_token,
        issue_number=issue_number,
        body=comment,
    )
    return {"success": success, "issue_number": issue_number}


@tool
def publish_heartbeat() -> dict:
    """Publish a CloudWatch heartbeat metric.

    This indicates the orchestrator is alive and running.
    Should be called periodically (e.g., every 60 seconds).

    Returns:
        Success status.
    """
    try:
        metrics = MetricsPublisher(enabled=True)
        success = metrics.publish_session_heartbeat()
        return {"success": success}
    except Exception as e:
        return {"error": str(e)}


@tool
def wait_seconds(seconds: int) -> dict:
    """Wait for a specified number of seconds.

    Use this between polling cycles to avoid rate limiting.

    Args:
        seconds: Number of seconds to wait (max 600).

    Returns:
        Confirmation of wait completion.
    """
    wait_time = min(seconds, 600)  # Cap at 10 minutes
    print(f"⏳ Waiting {wait_time} seconds...")
    time.sleep(wait_time)
    return {"waited_seconds": wait_time}


# =============================================================================
# Orchestrator System Prompt
# =============================================================================

ORCHESTRATOR_PROMPT = """You are an Orchestrator agent that manages GitHub issue builds.

## Your Role
You coordinate the issue-to-build workflow by:
1. Polling GitHub for approved issues (🚀 reaction from authorized approvers)
2. Claiming issues (adding agent-building label)
3. Starting worker containers via Step Functions
4. Monitoring build progress
5. Posting updates to GitHub issues
6. Publishing heartbeat metrics

## Workflow

### Main Loop
1. **Check for approved issues**: Call get_approved_issues()
2. **If issues found**:
   - Select the highest priority issue (first in list = most votes)
   - Claim it with claim_issue(issue_number)
   - Post a comment: "🤖 Starting build..."
   - Start the worker: start_worker_build(issue_number)
   - Monitor progress with check_worker_status(execution_arn)
3. **If no issues**: Wait for poll interval
4. **Always**: Publish heartbeat every 60 seconds

### On Worker Completion
- If SUCCEEDED: release_issue(issue_number, mark_complete=True)
- If FAILED: release_issue(issue_number, mark_complete=False), post error comment

### Error Handling
- If claim fails: Skip issue, try next one
- If worker start fails: Release issue, post error comment
- Always continue the main loop

## Important
- Only process ONE issue at a time
- Always publish heartbeat during waits
- Be resilient to transient errors
- Post informative comments to keep users updated
"""


# =============================================================================
# Main Entry Point
# =============================================================================


def create_orchestrator_client() -> ClaudeSDKClient:
    """Create the Claude Agent SDK client for the orchestrator."""
    # Apply provider configuration
    if PROVIDER == "bedrock":
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
        apply_provider_config(Provider.BEDROCK)
    else:
        apply_provider_config(Provider.ANTHROPIC)

    # Get API key if using Anthropic
    if PROVIDER == "anthropic":
        api_key = get_anthropic_api_key()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model="claude-sonnet-4-20250514",
            system_prompt=ORCHESTRATOR_PROMPT,
            allowed_tools=[
                "think",
                "get_approved_issues",
                "claim_issue",
                "release_issue",
                "start_worker_build",
                "check_worker_status",
                "post_issue_comment",
                "publish_heartbeat",
                "wait_seconds",
            ],
            max_turns=10000,  # Long-running orchestrator
        )
    )


def main():
    """Main entry point for the orchestrator."""
    print("=" * 60)
    print("🎯 Orchestrator Container Starting")
    print("=" * 60)
    print(f"📦 Repository: {GITHUB_REPO}")
    print(f"🔧 Provider: {PROVIDER}")
    print(f"⏱️  Poll interval: {POLL_INTERVAL}s")
    print(f"👥 Authorized approvers: {AUTHORIZED_APPROVERS}")
    print("=" * 60)

    # Validate configuration
    if not GITHUB_REPO:
        print("❌ GITHUB_REPOSITORY not set")
        return 1

    if not STATE_MACHINE_ARN:
        print("❌ STATE_MACHINE_ARN not set")
        return 1

    if not AUTHORIZED_APPROVERS:
        print("❌ AUTHORIZED_APPROVERS not set")
        return 1

    # Create client and start the main loop
    client = create_orchestrator_client()

    # Initial prompt to start the orchestrator loop
    initial_prompt = f"""You are now running as the Orchestrator.

Configuration:
- Repository: {GITHUB_REPO}
- Provider: {PROVIDER}
- Poll interval: {POLL_INTERVAL} seconds
- Environment: {ENVIRONMENT}

Start the main orchestration loop:
1. Publish an initial heartbeat
2. Check for approved issues
3. If found, process the highest priority issue
4. If not found, wait for the poll interval
5. Repeat indefinitely

Begin now."""

    try:
        # Run the orchestrator
        result = client.send_message(initial_prompt)
        print(f"\n📋 Orchestrator finished: {result}")
        return 0
    except KeyboardInterrupt:
        print("\n⚠️ Orchestrator interrupted")
        return 0
    except Exception as e:
        print(f"\n❌ Orchestrator error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
