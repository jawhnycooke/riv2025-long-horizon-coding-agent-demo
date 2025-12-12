#!/usr/bin/env python3
"""Orchestrator - Intelligent coordinator with MCP tools.

This orchestrator uses Claude Agent SDK with MCP servers for GitHub and AWS
operations, enabling intelligent issue triage, prioritization, and monitoring.

Architecture:
    Orchestrator (Claude Agent SDK + MCP)
        ├── GitHub MCP Server (issues, comments, labels)
        ├── AWS MCP Server (Step Functions)
        └── Built-in tools (heartbeat, wait)

Responsibilities:
    - Poll GitHub for issues approved with 🚀 reaction
    - Intelligent triage and prioritization
    - Claim issues by adding agent-building label
    - Start Step Functions execution with issue_number
    - Monitor worker progress
    - Post updates to GitHub issues
    - Publish CloudWatch heartbeat metrics

Environment Variables:
    GITHUB_REPOSITORY: Target repo (e.g., "owner/repo")
    GITHUB_TOKEN: GitHub PAT (for MCP server)
    ANTHROPIC_API_KEY: For Claude Agent SDK
    STATE_MACHINE_ARN: Step Functions state machine ARN
    PROVIDER: "anthropic" or "bedrock"
    AUTHORIZED_APPROVERS: Comma-separated GitHub usernames who can approve
    ENVIRONMENT: Environment name for CloudWatch metrics
    POLL_INTERVAL_SECONDS: How often to poll for new issues (default: 300)
    AWS_REGION: AWS region (default: us-west-2)
    AWS_PROFILE: AWS profile for MCP server (default: default)
"""

import os
import time
from datetime import UTC, datetime

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ProcessError,
    tool,
)

from src.cloudwatch_metrics import MetricsPublisher
from src.config import Provider, apply_provider_env, get_model_id
from src.secrets import (
    BEDROCK_API_KEY_ENV_VAR,
    get_anthropic_api_key,
    get_bedrock_api_key,
)

# =============================================================================
# Configuration
# =============================================================================

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
PROVIDER = os.environ.get("PROVIDER", "anthropic").lower()
ENVIRONMENT = os.environ.get("ENVIRONMENT", "reinvent")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

_approvers_env = os.environ.get("AUTHORIZED_APPROVERS", "")
AUTHORIZED_APPROVERS = [a.strip() for a in _approvers_env.split(",") if a.strip()]

# =============================================================================
# MCP Server Configuration
# =============================================================================

MCP_SERVERS = {
    "github": {
        "type": "stdio",
        "command": "npx",
        "args": [
            "-y",
            "@modelcontextprotocol/server-github"
        ],
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
        },
    },
    "aws": {
        "type": "stdio",
        "command": "npx",
        "args": [
            "-y",
            "@anthropic/mcp-server-aws",
            "--region", AWS_REGION,
        ],
    },
}

# =============================================================================
# Built-in Tools (not MCP)
# =============================================================================


@tool
def publish_heartbeat() -> dict:
    """Publish a CloudWatch heartbeat metric indicating the orchestrator is alive.

    Call this every 60 seconds during normal operation and during waits.
    GitHub Actions monitors this to detect stale sessions.

    Returns:
        Success status with timestamp.
    """
    try:
        metrics = MetricsPublisher(enabled=True)
        success = metrics.publish_session_heartbeat()
        timestamp = datetime.now(UTC).isoformat()
        return {"success": success, "timestamp": timestamp}
    except Exception as e:
        return {"error": str(e)}


@tool
def wait_seconds(seconds: int) -> dict:
    """Wait for a specified number of seconds.

    Use this between polling cycles. Remember to publish_heartbeat()
    before and after long waits.

    Args:
        seconds: Number of seconds to wait (max 600).

    Returns:
        Confirmation with actual wait time.
    """
    wait_time = min(seconds, 600)
    time.sleep(wait_time)
    return {"waited_seconds": wait_time, "timestamp": datetime.now(UTC).isoformat()}


# =============================================================================
# System Prompt - Goal-Oriented
# =============================================================================

SYSTEM_PROMPT = f"""You are an intelligent Orchestrator that coordinates GitHub issue builds.

## Your Mission
Ensure approved issues get built efficiently while keeping users informed and making smart decisions about what to build and when.

## Repository Context
- Repository: {GITHUB_REPO}
- Environment: {ENVIRONMENT}
- Authorized approvers: {', '.join(AUTHORIZED_APPROVERS) if AUTHORIZED_APPROVERS else '(none configured)'}
- Approval signal: 🚀 reaction from an authorized approver
- Building label: `agent-building`
- Complete label: `agent-complete`
- Step Functions ARN: {STATE_MACHINE_ARN}

## Available Tools

### GitHub MCP Server
You have full access to GitHub operations via the GitHub MCP server:
- **List issues**: Get open issues, filter by labels, check reactions
- **Read issue details**: Body, comments, metadata, linked issues
- **Post comments**: Keep users informed of progress
- **Manage labels**: Add/remove `agent-building`, `agent-complete`
- **Check reactions**: See who approved with 🚀

### AWS MCP Server
You have access to AWS Step Functions via the AWS MCP server:
- **Start execution**: Launch worker builds with issue context
- **Describe execution**: Check if RUNNING, SUCCEEDED, FAILED
- **List executions**: See all running/recent executions

### Built-in Tools
- `publish_heartbeat()` - Signal you're alive (call every 60s)
- `wait_seconds(n)` - Pause between actions (max 600s)

## Decision Framework

### 1. Issue Discovery
Find issues that are ready to build:
- Open issues with 🚀 reaction from authorized approvers
- NOT already labeled `agent-building` or `agent-complete`

### 2. Prioritization (Use Your Judgment)
When multiple issues are approved, consider:
- **Votes**: More 🚀 reactions = higher demand
- **Age**: Older issues have been waiting longer
- **Type**: Bugs before features? Depends on severity
- **Complexity**: Read the issue body, estimate effort
- **Dependencies**: Does it reference other issues?
- **Clarity**: Is it well-defined enough to build?

### 3. Triage (Before Claiming)
Before starting a build, assess the issue:
- Is the request clear and actionable?
- Does it have enough detail for the worker to build?
- Is it a duplicate of another open/closed issue?
- Are there unresolved questions in the comments?

If the issue is unclear:
- Post a comment asking for clarification
- Do NOT claim it yet
- Move to the next issue

### 4. Building
When you claim an issue:
1. Add `agent-building` label
2. Post a comment explaining what you understood and what will be built
3. Start Step Functions execution with:
   - issue_number
   - github_repo: {GITHUB_REPO}
   - provider: {PROVIDER}
   - environment: {ENVIRONMENT}

### 5. Monitoring
While a worker is running:
- Check status periodically (every 2-5 minutes)
- Post progress updates to the issue if you can infer progress
- Detect stuck builds (no activity for 30+ minutes)
- Keep publishing heartbeats

### 6. Completion Handling
On SUCCESS:
- Remove `agent-building` label
- Add `agent-complete` label
- Post a summary comment: what was built, branch name, how to test

On FAILURE:
- Remove `agent-building` label
- Do NOT add `agent-complete`
- Post a helpful comment explaining what went wrong
- Suggest next steps (retry, clarify requirements, etc.)

## Communication Guidelines

Write GitHub comments that are:
- **Concise**: Users don't want walls of text
- **Informative**: Include relevant details
- **Actionable**: Tell users what happens next
- **Human-friendly**: You're representing the team

### Comment Templates

**Starting build:**
```
🤖 **Starting Build**

I understood this issue as: [one sentence summary]

Building on branch `agent-runtime`. I'll post updates as progress is made.
```

**Progress update:**
```
📊 **Progress Update**

[What's been done so far]

Estimated time remaining: [if you can estimate]
```

**Build complete:**
```
✅ **Build Complete**

**What was built:**
- [bullet points]

**Branch:** `agent-runtime`
**To test:** [instructions if applicable]
```

**Build failed:**
```
❌ **Build Failed**

**What went wrong:** [brief explanation]

**Suggested next steps:**
- [actionable suggestions]
```

**Needs clarification:**
```
🤔 **Clarification Needed**

Before I can build this, could you clarify:
- [specific question]

I'll start the build once this is resolved.
```

## Constraints

- Process ONE issue at a time
- Always publish heartbeat every 60 seconds (especially during waits)
- Be resilient to transient GitHub/AWS errors (retry once, then skip)
- Never claim an issue you can't start building
- Don't spam issues with comments - be thoughtful

## Error Handling

- GitHub API rate limit: Wait and retry
- Step Functions start fails: Release issue, post error comment
- Transient network errors: Retry once, then continue
- Unknown errors: Log details, continue main loop

## Main Loop Structure

```
while True:
    publish_heartbeat()

    if currently_monitoring_a_build:
        check_status_and_handle_completion()
    else:
        issues = find_approved_issues()
        if issues:
            best_issue = prioritize_and_triage(issues)
            if best_issue:
                claim_and_start_build(best_issue)

    wait_seconds(poll_interval)
```

Remember: You are an intelligent agent, not a script. Use judgment, communicate well, and ensure builds succeed.
"""

# =============================================================================
# Initial Prompt
# =============================================================================

INITIAL_PROMPT = f"""You are now running as the Orchestrator for repository {GITHUB_REPO}.

**Current Configuration:**
- Poll interval: {POLL_INTERVAL} seconds
- Authorized approvers: {', '.join(AUTHORIZED_APPROVERS) if AUTHORIZED_APPROVERS else '(none configured)'}
- Provider: {PROVIDER}
- Environment: {ENVIRONMENT}

**Your first actions:**
1. Publish an initial heartbeat to signal you're online
2. Check for any issues with `agent-building` label (might be stale from a crash)
3. Look for approved issues (🚀 from authorized approvers)
4. If found, triage and start building the best candidate
5. If not found, wait for the poll interval
6. Continue indefinitely

**Important:** You have access to GitHub and AWS via MCP servers. Use the appropriate MCP tools for GitHub operations (listing issues, posting comments, managing labels) and AWS operations (Step Functions).

Begin now.
"""

# =============================================================================
# Main Entry Point
# =============================================================================


def create_orchestrator_client() -> ClaudeSDKClient:
    """Create the Claude Agent SDK client with MCP servers."""

    # Determine provider enum
    provider = Provider.BEDROCK if PROVIDER == "bedrock" else Provider.ANTHROPIC

    # Apply provider configuration
    apply_provider_env(provider)

    # Get API key based on provider
    if provider == Provider.ANTHROPIC:
        api_key = get_anthropic_api_key()
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            print("[ORCHESTRATOR] ⚠️ Warning: ANTHROPIC_API_KEY not set - API calls may fail")
            print("[ORCHESTRATOR]    Set via environment variable or AWS Secrets Manager")
    else:
        # Bedrock provider - check for API key authentication
        # See: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
        bedrock_api_key = get_bedrock_api_key()
        if bedrock_api_key:
            os.environ[BEDROCK_API_KEY_ENV_VAR] = bedrock_api_key
            print("[ORCHESTRATOR] 🔑 Using Bedrock API key authentication")
        elif os.environ.get(BEDROCK_API_KEY_ENV_VAR):
            print("[ORCHESTRATOR] 🔑 Using Bedrock API key from environment")
        else:
            # No API key - will fall back to IAM credentials
            print("[ORCHESTRATOR] 🔐 Using IAM credentials for Bedrock authentication")

    # Get the correct model ID for the provider
    model_id = get_model_id("sonnet", provider)
    print(f"[ORCHESTRATOR] 🤖 Using model: {model_id} (provider: {provider.value})")

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model_id,
            system_prompt=SYSTEM_PROMPT,
            # MCP servers provide GitHub and AWS tools
            mcp_servers=MCP_SERVERS,
            # Built-in tools + MCP tools
            allowed_tools=[
                "mcp__github__*",      # All GitHub MCP tools
                "mcp__aws__*",         # All AWS MCP tools
                "publish_heartbeat",   # Built-in
                "wait_seconds",        # Built-in
            ],
            max_turns=10000,  # Long-running orchestrator
            setting_sources=["project"],  # Load CLAUDE.md project instructions
        )
    )


def main():
    """Main entry point for the orchestrator."""
    print("=" * 60)
    print("[ORCHESTRATOR] 🎯 Intelligent Coordinator with MCP")
    print("=" * 60)
    print(f"[ORCHESTRATOR] 📦 Repository: {GITHUB_REPO}")
    print(f"[ORCHESTRATOR] 🔧 Provider: {PROVIDER}")
    print(f"[ORCHESTRATOR] ⏱️  Poll interval: {POLL_INTERVAL}s")
    print(f"[ORCHESTRATOR] 👥 Authorized approvers: {AUTHORIZED_APPROVERS}")
    print(f"[ORCHESTRATOR] 🔌 MCP Servers: GitHub, AWS")
    print(f"[ORCHESTRATOR] 🌍 AWS Region: {AWS_REGION}")
    print("=" * 60)

    # Validate configuration
    errors = []
    if not GITHUB_REPO:
        errors.append("GITHUB_REPOSITORY not set")
    if not STATE_MACHINE_ARN:
        errors.append("STATE_MACHINE_ARN not set")
    if not AUTHORIZED_APPROVERS:
        errors.append("AUTHORIZED_APPROVERS not set")
    if not os.environ.get("GITHUB_TOKEN"):
        errors.append("GITHUB_TOKEN not set")

    if errors:
        for err in errors:
            print(f"[ORCHESTRATOR] ❌ {err}")
        return 1

    # Create client and start
    print("\n[ORCHESTRATOR] 🚀 Starting orchestrator agent...")
    client = create_orchestrator_client()

    try:
        result = client.process(INITIAL_PROMPT)
        print(f"\n[ORCHESTRATOR] 📋 Finished: {result}")
        return 0
    except CLINotFoundError:
        print("\n[ORCHESTRATOR] ❌ Claude Code CLI not found")
        print("[ORCHESTRATOR]    Install: npm install -g @anthropic-ai/claude-code")
        return 2
    except CLIConnectionError as e:
        print(f"\n[ORCHESTRATOR] ❌ Failed to connect to Claude Code: {e}")
        return 2
    except ProcessError as e:
        print(f"\n[ORCHESTRATOR] ❌ Claude Code process failed (exit code {e.exit_code}): {e}")
        return 2
    except CLIJSONDecodeError as e:
        print(f"\n[ORCHESTRATOR] ❌ Failed to parse response from Claude Code: {e}")
        return 2
    except KeyboardInterrupt:
        print("\n[ORCHESTRATOR] ⚠️ Interrupted by user")
        return 0
    except ClaudeSDKError as e:
        print(f"\n[ORCHESTRATOR] ❌ SDK error: {e}")
        return 1
    except Exception as e:
        print(f"\n[ORCHESTRATOR] ❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
