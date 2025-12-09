# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

An autonomous agent system that builds React applications from GitHub issues using AWS Bedrock AgentCore and the Claude Agent SDK. The agent runs in long-horizon sessions (hours), managing its own git commits, testing via Playwright, and posting progress updates to GitHub issues.

## Setup & Configuration

### Interactive Setup (Recommended)

Run the setup wizard to configure your model provider:

```bash
# Install dependencies first (using uv for speed)
uv pip install -r requirements.txt

# Run the interactive setup wizard
python install.py
```

The wizard will guide you through:
1. **Provider selection**: Anthropic (Direct API) or Amazon Bedrock
2. **Model selection**: Claude Opus 4.5, Sonnet 4.5, or Haiku 4.5
3. **Region selection** (Bedrock only): us-east-1, us-west-2, eu-west-1
4. **API key configuration** (Anthropic only): Environment variable or direct input

Configuration is saved to `.claude-code.json` in the project directory.

### Configuration File Format

```json
{
  "provider": "anthropic",
  "model": "claude-opus-4-5-20251101",
  "bedrock": {
    "region": "us-east-1",
    "inference_profile": null
  },
  "anthropic": {
    "api_key_env_var": "ANTHROPIC_API_KEY"
  }
}
```

### Provider Options

| Provider | Authentication | Environment Variable |
|----------|---------------|---------------------|
| **Anthropic** | API key | `ANTHROPIC_API_KEY` |
| **Bedrock** | AWS credentials | `AWS_REGION` + IAM role or `aws configure` |

## Build & Run Commands

```bash
# Run the agent locally (creates ./generated-app)
python claude_code.py --project canopy

# Run with specific provider (overrides .claude-code.json)
python claude_code.py --project canopy --provider bedrock
python claude_code.py --project canopy --provider anthropic

# Run with custom ports
python claude_code.py --project canopy --frontend-port 6174 --backend-port 4001

# Run cleanup session (technical debt removal)
python claude_code.py --project canopy --cleanup-session

# Print prompts without running (debugging)
python claude_code.py --project canopy --print-prompts

# Run enhancement mode on existing codebase
python claude_code.py --enhance-feature path/to/FEATURE_REQUEST.md --existing-codebase ./generated-app

# Dry run - validate configuration without executing
python claude_code.py --dry-run --project canopy

# Dry run with provider override
python claude_code.py --dry-run --project canopy --provider anthropic

# Install dependencies
uv pip install -r requirements.txt
```

### Dry Run Mode

The `--dry-run` flag simulates agent execution without making API calls. It performs:

1. **Configuration validation** - Verifies `.claude-code.json` exists and is valid
2. **Credential validation** - Checks AWS credentials (Bedrock) or API key (Anthropic)
3. **Prompt validation** - Ensures BUILD_PLAN.md and system_prompt.txt exist
4. **Execution plan display** - Shows what would be executed

**Exit codes:**
- `0` - Configuration valid, agent would run successfully
- `1` - Configuration invalid or missing required files

**Use cases:**
- CI/CD validation before deployment
- Pre-flight checks before long-running sessions
- Debugging configuration issues

## Architecture

### Entry Points

**`install.py`** - Interactive CLI setup wizard
- Menu-driven configuration for provider selection (Anthropic or Bedrock)
- Model and region selection
- Persists configuration to `.claude-code.json`
- Supports re-running to update existing configuration

**`bedrock_entrypoint.py`** - AWS Bedrock AgentCore runtime wrapper
- Handles GitHub issue-driven workflow: clones repo, sets up branches, manages git hooks
- Publishes CloudWatch heartbeat metrics for session health monitoring
- Runs in Docker on ECS Fargate with EFS persistence
- Fetches secrets from AWS Secrets Manager (Anthropic API key, GitHub tokens)
- Supports both "legacy mode" (PROJECT_NAME env var) and "GitHub mode" (issue-driven builds)
- Reads `PROVIDER` environment variable to select Anthropic or Bedrock

**`claude_code.py`** - Core agent session manager
- Wraps Claude Agent SDK (`ClaudeSDKClient`) with custom tools and hooks
- Loads configuration from `.claude-code.json` (CLI args override config)
- Sets `CLAUDE_CODE_USE_BEDROCK=1` environment variable for Bedrock provider
- Manages agent state machine: `continuous`, `run_once`, `run_cleanup`, `pause`, `terminated`
- State persisted in `agent_state.json` for Mission Control integration
- Implements completion detection (`🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED`)
- Token tracking with cost limits (MAX_COST_USD = 5000)

### Core Modules (`src/`)

- **`git_manager.py`** - Centralized git operations: cloning, branching, post-commit hooks for auto-push
- **`github_integration.py`** - Issue lifecycle: approval via 🚀 reaction, labels (agent-building, agent-complete)
- **`security.py`** - Hook validators: path sandboxing, bash command allowlist, bulk tests.json modification prevention
- **`session_manager.py`** - Session setup: template copying, prompt templating, bootstrap files
- **`cloudwatch_metrics.py`** - Heartbeat metrics for session health monitoring
- **`token_tracker.py`** - Token usage tracking with warning thresholds

### GitHub Actions Workflows

- **`issue-poller.yml`** - Runs every 5 min, checks for 🚀-approved issues and session health via CloudWatch heartbeat
- **`agent-builder.yml`** - Invokes AgentCore when issue approved, uses global lock to prevent race conditions
- **`deploy-preview.yml`** - Deploys completed builds to CloudFront
- **`stop-agent-on-close.yml`** - Cleanup when issues are closed

### Security Model

The agent is sandboxed via hooks in `src/security.py`:
- `universal_path_security_hook` - Blocks file operations outside project directory
- `bash_security_hook` - Allowlist of safe commands (npm, npx, git, etc.)
- `track_read_hook` - Tracks file reads for screenshot verification workflow

Blocked patterns:
- Bulk modification of `tests.json` via sed/awk/jq/python (must use Edit tool with screenshot verification)
- Commands outside allowlist in `src/config.py`

### Security Error Messages

All security hook rejections provide actionable error messages via `src/error_messages.py`:

**Message Format:**
```
🚫 [TYPE] BLOCKED: [brief description]

[Details about what was attempted]

💡 How to fix:
  • [Specific actionable suggestion]
  • [Alternative approach]
```

**Error Categories:**

| Category | Error Types | Example Suggestion |
|----------|-------------|-------------------|
| **Path Validation** | Outside project, no project root | Use relative paths within project |
| **Bash Commands** | Not in allowlist, rm restricted | Use Edit tool for file operations |
| **Git Operations** | git init blocked | Use existing repository |
| **Test Verification** | No screenshot, screenshot not viewed | Take and view screenshot first |

All blocked actions are logged to the audit trail for security review.

### OpenTelemetry Tracing

The agent supports distributed tracing via OpenTelemetry for observability of tool calls.

**Configuration** (in `.claude-code.json`):
```json
{
  "tracing": {
    "enabled": true,
    "service_name": "claude-code-agent",
    "exporter": "console",
    "otlp_endpoint": "http://localhost:4317"
  }
}
```

**Settings:**
| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `false` | Enable/disable tracing |
| `service_name` | `claude-code-agent` | Service name in traces |
| `exporter` | `console` | Export method: `console`, `otlp`, or `none` |
| `otlp_endpoint` | `null` | OTLP collector endpoint (for `otlp` exporter) |

**Environment Variable Override:**
- `OTEL_TRACING_ENABLED=true` - Enables tracing regardless of config
- `OTEL_TRACING_ENABLED=false` - Disables tracing regardless of config
- `OTEL_EXPORTER_OTLP_ENDPOINT` - Fallback OTLP endpoint if not in config

**Exporter Types:**
- `console` - Prints spans to stdout (useful for debugging)
- `otlp` - Sends spans to an OpenTelemetry Collector via gRPC
- `none` - Tracing enabled but no export (in-memory only, for testing)

**What's Traced:**
- All tool calls (Bash, Edit, Read, Write, etc.)
- Tool input preview (first 500 chars)
- Tool result preview (first 500 chars)
- Duration in milliseconds
- Success/error status

**Example Output (console exporter):**
```
{
    "name": "tool_call.Bash",
    "context": {...},
    "attributes": {
        "tool.name": "Bash",
        "tool.input_preview": "{'command': 'npm test'}",
        "tool.duration_ms": 1234.56,
        "tool.result_preview": "PASS..."
    }
}
```

### Agent State Machine

State is controlled via `agent_state.json` in the generation directory:
```json
{
  "desired_state": "continuous",  // or "run_once", "run_cleanup", "pause", "terminated"
  "current_state": "continuous",
  "timestamp": "2025-01-15T23:52:09.505Z",
  "setBy": "agent",
  "note": "Running in continuous mode",
  "build_plan_version": "1.0.0"  // from BUILD_PLAN.md YAML frontmatter
}
```

### Session Lock Management

The agent-builder workflow uses a distributed lock mechanism to prevent race conditions when multiple issues are approved simultaneously. The lock is implemented using the `agent-building` GitHub label combined with a GitHub Actions concurrency group.

**Lock Features:**
- **Jitter**: Random 0-5 second delay before lock acquisition to reduce thundering herd
- **Timeout**: Configurable lock timeout (default: 10 minutes / 600 seconds)
- **Stale Lock Release**: Automatically releases locks that exceed the timeout threshold
- **Status Outputs**: Lock status queryable via GitHub Actions workflow outputs

**Configuration** (via GitHub repository variables):
| Variable | Default | Description |
|----------|---------|-------------|
| `LOCK_TIMEOUT_SECONDS` | `600` | Lock timeout in seconds (10 minutes) |
| `HEARTBEAT_STALENESS_SECONDS` | `300` | Session heartbeat staleness threshold |

**Workflow Outputs** (from `acquire-runtime-lock` job):
| Output | Description |
|--------|-------------|
| `lock_acquired` | Whether this workflow acquired the lock |
| `lock_age_seconds` | How long the existing lock was held |
| `stale_lock_released` | Whether a stale lock was auto-released |
| `lock_holder_issue` | Issue number holding the lock |

**Check Lock Status Manually:**
```bash
# Using the helper script
GITHUB_TOKEN=your_token python .github/scripts/check_lock_status.py --repo owner/repo

# Using gh CLI directly
gh api repos/OWNER/REPO/issues -q '.[] | select(.labels[].name == "agent-building") | .number'
```

**Deadlock Recovery:**
If the agent crashes and leaves a stale lock:
1. The lock will auto-release after 10 minutes (configurable)
2. Alternatively, manually remove the label: `gh issue edit ISSUE_NUMBER --remove-label agent-building`
3. The issue poller will detect the stale session via CloudWatch heartbeat and trigger a restart

## Key Conventions

### Tests JSON Verification

The agent must verify each test in `tests.json` by:
1. Taking a screenshot using Playwright
2. Capturing console output
3. Viewing both via Read tool
4. Only then marking test as passing via Edit tool

System blocks bulk modifications to prevent cheating.

### Prompts Structure

- `prompts/system_prompt.txt` - Generic system prompt (no templating)
- `prompts/<project>/BUILD_PLAN.md` - Project-specific build specification (required)
- `prompts/<project>/DEBUGGING_GUIDE.md` - Optional debugging context

### BUILD_PLAN.md Versioning

BUILD_PLAN.md files support YAML frontmatter with a version field:

```markdown
---
version: "1.0.0"
---

<project_specification>
  ...
</project_specification>
```

The version is:
- Logged at session start (`📋 BUILD_PLAN.md version: X.X.X`)
- Stored in `agent_state.json` under `build_plan_version`
- Included in GitHub issue comments when sessions start

**Versioning Scheme**: Use semantic versioning (MAJOR.MINOR.PATCH):
- **MAJOR**: Breaking changes to project specification
- **MINOR**: New features or requirements added
- **PATCH**: Clarifications, typo fixes, documentation updates

This enables tracking which version of the spec was used for each build session.

### Generated App Structure

The agent creates React+Vite+Tailwind apps in `generated-app/`:
- `tests.json` - E2E test specifications with pass status
- `claude-progress.txt` - Progress notes for session continuity
- `init.sh` - Server startup script for continuation sessions
- `screenshots/` - Playwright verification screenshots
- `logs/` - Session JSON logs

### Completion Signal

Agent signals completion with a configurable message. Default: `🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED`

**Configuration** (in `.claude-code.json`):
```json
{
  "completion_signal": {
    "signal": "🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED",
    "emoji": "🎉",
    "complete_phrase": "implementation complete",
    "finished_phrase": "all tasks finished"
  }
}
```

**Settings:**
| Field | Default | Description |
|-------|---------|-------------|
| `signal` | `🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED` | Full completion message output by agent |
| `emoji` | Auto-extracted from signal, or `🎉` | Emoji marker for detection |
| `complete_phrase` | `implementation complete` | Phrase to detect (case-insensitive) |
| `finished_phrase` | `all tasks finished` | Second phrase to detect (case-insensitive) |

**Detection Logic:**
The completion signal is detected when ALL of the following are present in agent output:
1. The configured emoji character
2. The `complete_phrase` (case-insensitive)
3. The `finished_phrase` (case-insensitive)

**Custom Signal Examples:**
```json
// Minimal config - just change the signal, phrases auto-extracted
{
  "completion_signal": {
    "signal": "✅ BUILD COMPLETE - ALL TESTS PASSED"
  }
}

// Full customization
{
  "completion_signal": {
    "signal": "🚀 LAUNCH SUCCESSFUL",
    "emoji": "🚀",
    "complete_phrase": "launch successful",
    "finished_phrase": "launch successful"
  }
}
```

**What Triggers on Completion:**
1. State transition to `pause`
2. `agent-complete` label on GitHub issue
3. Deploy preview workflow

## Infrastructure

AWS CDK stack in `infrastructure/`:
- ECS Fargate cluster with EFS persistence
- ECR repository for Docker images
- CloudWatch logs and alarms
- AWS Backup for daily EFS snapshots

Deploy: `cd infrastructure && cdk deploy`
