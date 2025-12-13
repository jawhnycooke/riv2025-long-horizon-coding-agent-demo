# Long-Horizon Agent Patterns

This documentation maps how this project implements the patterns from Anthropic's ["Effective Harnesses for Long-Running Agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) article.

## Overview

This project implements the patterns from the article to build React applications from GitHub issues autonomously. The article recommends key infrastructure for long-horizon coding sessions:

- **Feature list** (`feature_list.json`) - JSON file with passes boolean to prevent cheating
- **Progress log** (`claude-progress.txt`) - Chronological log for context recovery
- **Init script** (`init.sh`) - Development server startup for session continuity
- **Git commits** - Recovery points for state history

## Pattern Index

| Pattern | Article Recommendation | Our Implementation | Documentation |
|---------|----------------------|-------------------|---------------|
| Feature List | JSON file with passes boolean | `feature_list.json` | [feature-list.md](./feature-list.md) |
| Progress Tracking | Chronological log for context recovery | `claude-progress.txt` | [progress-tracking.md](./progress-tracking.md) |
| Session Recovery | Git commits as recovery points | State machine + git | [session-recovery.md](./session-recovery.md) |
| Verification | Screenshot-based testing | Playwright workflow | [verification.md](./verification.md) |

## Architecture

```mermaid
flowchart TB
    SessionMgr["claude_code_agent.py<br/>(Session Manager)"]
    Claude["🤖 Claude Agent<br/>(Claude Agent SDK)"]
    Files["📁 State Files<br/>feature_list.json, claude-progress.txt"]
    Git["📦 Git<br/>Commits as checkpoints"]

    SessionMgr -->|"creates"| Claude
    Claude -->|"reads/writes"| Files
    Claude -->|"commits"| Git
```

**Session Manager** (`claude_code_agent.py`): Manages session lifecycle, state machine, completion detection.

**Claude Agent**: Reads state files, implements features, runs tests, commits changes.

## Session Startup Sequence

From the article's recommendations, each session should:

1. **Confirm directory**: `pwd` to verify working directory
2. **Read progress files**: `feature_list.json`, `claude-progress.txt`
3. **Check git history**: Recent commits for context
4. **Select feature**: Pick highest-priority incomplete feature
5. **Run init script**: Execute `init.sh` for dev infrastructure
6. **Verify baseline**: Run E2E tests before making changes

## Key Files

| File | Purpose | Location |
|------|---------|----------|
| `feature_list.json` | Feature list with passes boolean | `generated-app/feature_list.json` |
| `claude-progress.txt` | Chronological progress log | `generated-app/claude-progress.txt` |
| `init.sh` | Development server startup | `generated-app/init.sh` |
| `agent_state.json` | Session state machine | `generated-app/agent_state.json` |

## Why These Patterns Matter

### Discourages "Cheating"
> "Using JSON for feature_list.json adds friction that discourages the model from bulk-editing feature statuses"

The agent must verify each test with a screenshot before marking it as passing.

### Enables Recovery
> "Git commits serve as recovery points... the agent can reset to a known good state"

If something goes wrong, we can restore from the last commit.

### Maintains Context
> "claude-progress.txt files documenting previous work"

Each session starts by reading what was done before, enabling clean handoffs.

### Ensures Quality
> "Screenshot verification proves the UI actually works"

Visual confirmation that features render correctly, not just that code compiles.

## Further Reading

- [Feature List Pattern](./feature-list.md) - How `feature_list.json` works
- [Progress Tracking Pattern](./progress-tracking.md) - The `claude-progress.txt` format
- [Session Recovery Pattern](./session-recovery.md) - Git and state machine
- [Verification Pattern](./verification.md) - Screenshot workflow
