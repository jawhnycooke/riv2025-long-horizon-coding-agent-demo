# CLAUDE.md

Development guide for the Long-Horizon Coding Agent.

## Overview

Harness-enforced two-container ECS/Fargate architecture that builds React applications from GitHub issues using Claude Agent SDK with MCP servers.

```mermaid
flowchart LR
    subgraph Orchestrator["Orchestrator Container"]
        OPy["orchestrator.py"]
        GMCP["GitHub MCP"]
        AMCP["AWS MCP"]
    end

    subgraph Worker["Worker Container"]
        Harness["Worker Harness"]
        Agent["Claude Agent"]
        PMCP["Playwright MCP"]
    end

    GitHub["GitHub Issues"] --> GMCP
    GMCP --> OPy
    OPy --> AMCP
    AMCP -->|"Step Functions"| Harness
    Harness --> Agent
    Agent --> PMCP
    Agent -->|"Commit"| GitHub
```

## Entry Points

| File | Container | Purpose |
|------|-----------|---------|
| `orchestrator.py` | Orchestrator | Goal-oriented AI with GitHub/AWS MCP for intelligent issue triage |
| `worker_main.py` | Worker | **Harness-based** entry point (preferred) |
| `claude_code_agent.py` | Worker | Legacy entry point (backward compatibility) |

## Run Commands

```bash
# Local development - harness-based worker
ISSUE_NUMBER=42 GITHUB_REPOSITORY=owner/repo python worker_main.py

# Local development - legacy worker
python claude_code_agent.py --project canopy

# Docker Compose
docker-compose up orchestrator  # Long-running
docker-compose up worker        # One-shot build

# Install dependencies
pip install -r requirements.txt
```

## Harness-Enforced Architecture

Based on Anthropic's ["Effective Harnesses for Long-Running Agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents).

### Failure Mode Prevention

| Failure Mode | Problem | Harness Solution |
|--------------|---------|------------------|
| **Premature Completion** | Agent declares "done" early | Harness validates tests.json |
| **Incomplete Implementation** | Half-finished features | ONE test per session |
| **Inadequate Testing** | No verification | Must view screenshot |
| **Inefficient Onboarding** | Token waste | Harness runs setup |

### Responsibility Separation

```mermaid
flowchart TB
    subgraph Harness["HARNESS (Python) - Workflow"]
        H1["Setup environment"]
        H2["Run smoke test"]
        H3["Select ONE test"]
        H4["Build focused prompt"]
        H5["Validate completion"]
        H6["Determine exit status"]
    end

    subgraph Agent["AGENT (Claude) - Coding"]
        A1["Implement feature"]
        A2["Take screenshots"]
        A3["Mark test pass"]
        A4["Commit changes"]
    end

    H1 --> H2 --> H3 --> H4 --> A1
    A1 --> A2 --> A3 --> A4 --> H5 --> H6
```

**Harness decides:** What to work on, when complete, exit status
**Agent decides:** How to implement, code quality, when to commit

### Orchestrator Internals

```mermaid
flowchart TB
    subgraph Orc["orchestrator.py"]
        subgraph MCP["MCP Servers"]
            GH["GitHub MCP<br/>@modelcontextprotocol/server-github"]
            AWS["AWS MCP<br/>@anthropic/mcp-server-aws"]
        end

        subgraph Tools["Built-in Tools"]
            HB["publish_heartbeat()"]
            WS["wait_seconds()"]
        end

        subgraph Agent["Claude Agent"]
            SP["System Prompt (314 lines)"]
            AI["Goal-Oriented Decisions"]
        end
    end

    GH -->|"list_issues, add_label<br/>post_comment"| Agent
    AWS -->|"start_execution<br/>describe_execution"| Agent
    Tools --> Agent
```

### Worker Internals

```mermaid
flowchart TB
    subgraph Worker["worker_main.py"]
        subgraph Harness["WorkerHarness"]
            direction TB
            B1["setup_environment()"]
            B2["start_dev_servers()"]
            B3["run_smoke_test()"]
            B4["select_next_task()"]
            B5["build_agent_prompt()"]
            A1["verify_commit_made()"]
            A2["check_test_status()"]
            A3["determine_exit_status()"]
            A4["push_changes()"]
        end

        subgraph Agent["Claude Agent"]
            subgraph PMCP["Playwright MCP"]
                SS["screenshot"]
                CL["click"]
                FL["fill"]
            end
            subgraph SDK["SDK Tools"]
                RD["Read"]
                WR["Write"]
                ED["Edit"]
                BA["Bash"]
            end
            subgraph Hooks["Security Hooks"]
                PH["Path Hook"]
                BH["Bash Hook"]
                TH["Track Hook"]
            end
        end

        subgraph Cfg["Config Classes"]
            WC["WorkerConfig"]
            TT["TestTask"]
            WS2["WorkerStatus"]
        end
    end

    B1 --> B2 --> B3 --> B4 --> B5
    B5 --> Agent
    Agent --> A1 --> A2 --> A3 --> A4
    SDK --> Hooks
```

### Worker Exit Codes

| Code | Status | Meaning |
|------|--------|---------|
| 0 | `CONTINUE` | Test passed, more remain |
| 1 | `COMPLETE` | All tests pass |
| 2 | `FAILED` | Unrecoverable error |
| 3 | `BROKEN_STATE` | Smoke test failed |

## MCP Servers

### Orchestrator

| Server | Package | Purpose |
|--------|---------|---------|
| GitHub | `@modelcontextprotocol/server-github` | Issues, labels, comments |
| AWS | `@anthropic/mcp-server-aws` | Step Functions |

### Worker

| Server | Package | Purpose |
|--------|---------|---------|
| Playwright | `@anthropic/mcp-server-playwright` | Browser automation |

## Orchestrator Flow

```mermaid
flowchart TD
    Start([Start]) --> Poll["Poll GitHub via MCP"]
    Poll --> Check{Approved issues?}
    Check -->|No| Heartbeat[publish_heartbeat]
    Heartbeat --> Wait[wait_seconds]
    Wait --> Poll

    Check -->|Yes| Triage["Intelligent triage<br/>& prioritization"]
    Triage --> Claim["Add agent-building label<br/>via GitHub MCP"]
    Claim --> Comment["Post comment via MCP"]
    Comment --> Invoke["Start Step Functions<br/>via AWS MCP"]
    Invoke --> Monitor[Monitor execution]
    Monitor --> Done{Done?}
    Done -->|No| Monitor
    Done -->|Yes| Release[Update labels via MCP]
    Release --> Poll
```

## Worker Flow (Harness-Enforced)

```mermaid
flowchart TD
    Start([Start Worker]) --> Setup["HARNESS: Setup<br/>Clone, branch, servers"]
    Setup --> Smoke{"HARNESS: Smoke test<br/>App loads?"}

    Smoke -->|Fail| Broken([Exit 3: BROKEN])
    Smoke -->|Pass| Select["HARNESS: Select ONE test"]

    Select --> Any{Tests remaining?}
    Any -->|No| Complete([Exit 1: COMPLETE])
    Any -->|Yes| Prompt["HARNESS: Build focused prompt"]

    Prompt --> Implement["AGENT: Implement"]
    Implement --> Screenshot["AGENT: Screenshot via MCP"]
    Screenshot --> Verify["AGENT: Verify visually"]
    Verify --> Mark["AGENT: Mark pass"]
    Mark --> Commit["AGENT: Commit"]

    Commit --> Validate["HARNESS: Validate"]
    Validate --> Passed{Test passing?}
    Passed -->|No| Retry{Retry limit?}
    Retry -->|No| Continue([Exit 0: CONTINUE])
    Retry -->|Yes| Failed([Exit 2: FAILED])
    Passed -->|Yes| Push["HARNESS: Push"]
    Push --> AllDone{All pass?}
    AllDone -->|Yes| Complete
    AllDone -->|No| Continue2([Exit 0: CONTINUE])
```

## Core Modules

| Module | Purpose |
|--------|---------|
| `src/worker_harness.py` | Harness enforcing agent constraints |
| `src/worker_config.py` | Configuration dataclasses |
| `src/secrets.py` | AWS Secrets Manager utilities |
| `src/github_integration.py` | GitHub API (labels, comments, issues) |
| `src/security.py` | Security hooks (path validation, command allowlist) |
| `src/cloudwatch_metrics.py` | Heartbeat and metrics publishing |
| `src/git_manager.py` | Git operations (clone, branch, commit) |

## Security Model

```mermaid
flowchart LR
    subgraph Agent["Claude Agent"]
        Tools["Tool Calls"]
    end

    subgraph Hooks["Security Hooks"]
        Path["Path Validator"]
        Bash["Bash Allowlist"]
        Test["Screenshot Tracker"]
    end

    Tools --> Path & Bash & Test

    Path -->|"✗ External"| Block["Block"]
    Path -->|"✓ Internal"| Allow["Allow"]
    Bash -->|"✗ Dangerous"| Block
    Bash -->|"✓ Safe"| Allow
```

**Allowed Bash:** npm, npx, node, git, python, playwright
**Blocked:** rm -rf, curl external, paths outside project

## Environment Variables

```bash
# Required for worker
ISSUE_NUMBER=42
GITHUB_REPOSITORY=owner/repo

# Required for orchestrator
STATE_MACHINE_ARN=arn:aws:states:...
AUTHORIZED_APPROVERS=user1,user2
GITHUB_TOKEN=ghp_...

# Optional
PROVIDER=anthropic           # or "bedrock"
AGENT_BRANCH=agent-runtime
ENVIRONMENT=local
MAX_RETRIES_PER_TEST=3
SMOKE_TEST_TIMEOUT=30
DEV_SERVER_PORT=6174
AWS_REGION=us-west-2
```

## Infrastructure (CDK)

```mermaid
flowchart TB
    subgraph Stacks["CDK Stacks"]
        Core["claude-code-stack.ts<br/>VPC, ECR, EFS, S3, Secrets"]
        ECS["ecs-cluster-stack.ts<br/>Cluster, Task Definitions"]
        SFN["step-functions-stack.ts<br/>Worker State Machine"]
    end

    Core --> ECS --> SFN
```

Deploy:
```bash
cd infrastructure
npm install
cdk deploy --all
```

## Key Files

```
├── orchestrator.py              # Orchestrator with GitHub/AWS MCP
├── worker_main.py               # Harness-based worker entry
├── claude_code_agent.py         # Legacy worker entry
├── src/
│   ├── worker_harness.py        # Harness logic
│   ├── worker_config.py         # Config dataclasses
│   ├── secrets.py               # AWS Secrets Manager
│   ├── github_integration.py    # GitHub API
│   ├── security.py              # Security hooks
│   └── cloudwatch_metrics.py    # Metrics
├── prompts/
│   ├── system_prompt.txt        # Full system prompt (legacy)
│   └── worker_system_prompt.txt # Simplified worker prompt
├── infrastructure/lib/
│   ├── claude-code-stack.ts     # Core infra
│   ├── ecs-cluster-stack.ts     # ECS cluster
│   └── step-functions-stack.ts  # Step Functions
├── Dockerfile.orchestrator      # Node.js for MCP
├── Dockerfile.worker            # Node.js for MCP
└── docker-compose.yml
```

## Test Verification

The harness enforces screenshot verification:

**Screenshot Path Pattern (required):**
```
screenshots/issue-{issue_number}/{test_id}-*.png
```
Example: `screenshots/issue-42/sidebar-collapse-1702345678.png`

**Verification Process:**
1. Agent takes Playwright screenshot via MCP with correct path
2. Agent checks MCP output for console errors (shown in tool response)
3. Agent reads screenshot with Read tool to verify visually
4. Only then can agent mark test as passing (Edit tool on tests.json)
5. Harness validates tests.json after agent exits

**Console Error Detection:**
- Playwright MCP includes console output in its response
- Agent reviews MCP output for `console.error` or `console.warn`
- Console log files (`.txt`) are optional - not required for MCP workflow

Security hooks block bulk modification of tests.json.

## Completion

The **harness** (not the agent) determines completion by reading tests.json:
- All tests status = "pass" → Exit 1 (COMPLETE)
- Assigned test not passing → Exit 0 (CONTINUE) or Exit 2 (FAILED)

This prevents premature completion claims by the agent.
