# Exploration: Full Codebase Architecture

**Date**: 2025-12-03 | **Scope**: Medium | **Status**: ✅ Complete

## 1. Foundation (What exists)

**Tech stack**: Python 3.12, Claude Agent SDK, AWS Bedrock AgentCore, boto3, GitHub Actions

**Architecture**: Long-horizon autonomous agent system for building React applications from GitHub issues
- Runs multi-hour sessions autonomously
- Self-manages git commits, Playwright testing, and GitHub issue updates
- Deploys via AWS Bedrock AgentCore on ECS Fargate with EFS persistence

**Structure**:
- `claude_code.py` - Core agent session manager (entry point for local development)
- `bedrock_entrypoint.py` - AWS runtime wrapper (entry point for cloud)
- `src/` - Core modules (security, git, GitHub, sessions, metrics, logging, tokens)
- `prompts/` - System prompts and project-specific BUILD_PLAN files
- `frontend-scaffold-template/` - Vite+React+Tailwind template for generated apps
- `infrastructure/` - AWS CDK stack
- `.github/workflows/` - GitHub Actions (issue polling, agent building, deploy)

**CLAUDE.md instructions**: Already present at `/Users/jawcooke/Documents/Projects/riv2025-long-horizon-coding-agent-demo/CLAUDE.md` - comprehensive guide created during this session.

## 2. Patterns (How it's built)

**Architectural patterns**:

- **Agent State Machine** (`claude_code.py:78-120`):
  - States: `continuous`, `run_once`, `run_cleanup`, `pause`, `terminated`
  - Persisted in `agent_state.json` for Mission Control integration
  - State transitions controlled via external file modifications

- **Hook-Based Security** (`src/security.py`):
  - `universal_path_security_hook` - Sandboxes file operations to project directory
  - `bash_security_hook` - Allowlist-based command filtering
  - `track_read_hook` - Tracks file reads for screenshot verification workflow
  - Hooks registered with Claude Agent SDK

- **GitHub Issue-Driven Workflow** (`src/github_integration.py`):
  - Issues labeled `agent` trigger builds via GHA
  - 🚀 reaction = approval to start
  - `agent-building` label during work
  - `agent-complete` label on finish

- **Session Resumption Pattern** (`src/session_manager.py`):
  - Checks for `claude-progress.txt` to continue interrupted sessions
  - Reads `agent_state.json` to restore state
  - Loads token counts from `logs/*.json` for cost tracking continuity

**Testing patterns**:
- E2E tests defined in `tests.json` with screenshot verification
- Agent must view screenshot AND console log via Read tool before marking test as passing
- Bulk modification of `tests.json` blocked by security hooks
- Completion signal: `🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED`

**Error handling**:
- Exit codes used throughout for agent-compatible error reporting
- `MetricsPublisher.publish_error()` sends to CloudWatch
- Token/cost limits enforced via `TokenTracker.check_limits()` with hard exit

## 3. Constraints (What limits decisions)

**Technical**:
- Python 3.12+ (Docker image: `python:3.12-slim`)
- Claude Agent SDK required for agent operations
- AWS Bedrock AgentCore for cloud deployment
- Node.js required for Playwright and generated app

**Quality**:
- Tests.json verification workflow enforced via hooks
- Console errors must be fixed before test can pass
- `npm run build` must succeed before completion

**Security**:
- Bash commands allowlisted in `src/config.py:33-74`
- File operations sandboxed to project directory
- Blocked patterns for `tests.json` modification: sed, awk, jq, python, node, redirects

**Operational**:
- MAX_COST_USD = $5,000 hard limit
- MAX_API_CALLS = 5,000 hard limit
- CloudWatch heartbeat required for session health monitoring
- EFS persistence for cross-session state

**Generated App Constraints** (from BUILD_PLAN.md):
- React 18 + Vite 6 + Tailwind CSS v4
- Dexie.js for IndexedDB persistence (no backend)
- Static build output only (`npm run build` → `dist/`)
- Forest canopy design palette required

## 4. Reusability (What to leverage)

**Frontend scaffold** (`frontend-scaffold-template/`):
- Pre-configured Vite + React + Tailwind
- shadcn/ui components via Radix UI
- dnd-kit for drag-and-drop
- Recharts for dashboards
- Framer Motion for animations

**Core modules** (in `src/`):
- `git_manager.py` - Git operations with auto-push hooks
- `github_integration.py` - Issue/label management
- `cloudwatch_metrics.py` - CloudWatch metrics publishing
- `token_tracker.py` - Token/cost tracking with limits
- `logging_utils.py` - Session logging with JSON export

**Prompt templating** (`src/session_manager.py`):
- Variables: `{{frontend_port}}`, `{{backend_port}}`, `{{project_name}}`
- Applied to `.txt` and `.md` files

## 5. Handoff (What's next)

**For PLAN**:
- Agent operates autonomously from BUILD_PLAN.md
- No server/API - purely static React app with IndexedDB
- Security hooks prevent certain bash commands

**For CODE**:
- Run locally: `python claude_code.py --project canopy`
- Frontend dev server: `pnpm dev` (port 6174)
- Screenshots: `node playwright-test.cjs --url http://localhost:6174 --test-id <ID> --output-dir screenshots/issue-$ISSUE_NUMBER --operation full`
- Build: `npm run build`

**For COMMIT**:
- Git hooks auto-push on commit (when in AgentCore)
- No commit message attribution to Claude
- Signal completion with: `🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED`

**Gaps**:
- No test coverage requirements for agent code itself
- No linting/formatting enforced on Python code
- Enhancement mode (`--enhance-feature`) workflow less documented

---

**Files Examined**: 18 primary files across `src/`, `prompts/`, `infrastructure/`, `.github/workflows/`

**Patterns Documented**: 5 (state machine, hook security, GitHub workflow, session resumption, test verification)

**Recommended next phase**: This is an autonomous agent system - typically driven by GitHub issues rather than manual development. For enhancements to the agent itself, use `/epcc-plan [enhancement-area]`.
