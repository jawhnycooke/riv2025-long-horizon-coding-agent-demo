# Long-Horizon Coding Agent

An autonomous agent system that builds React applications from GitHub issues using Claude Agent SDK on AWS ECS/Fargate.

## Architecture

This system implements the **harness-enforced agent pattern** from Anthropic's ["Effective Harnesses for Long-Running Agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) article, preventing common agent failure modes through code enforcement rather than prompt instructions.

### Agent Failure Mode Prevention

| Failure Mode | Problem | Harness Solution |
|--------------|---------|------------------|
| **Premature Completion** | Agent declares "done" after partial work | Harness validates all tests pass via feature_list.json |
| **Incomplete Implementation** | Half-finished features | Harness assigns ONE test per session |
| **Inadequate Testing** | Marks complete without verification | Harness validates screenshot exists + was viewed |
| **Inefficient Onboarding** | Wastes tokens on environment setup | Harness runs init.sh and smoke tests before agent |

### System Overview

```mermaid
flowchart TB
    subgraph GitHub["GitHub Repository"]
        Issues["Issues"]
        Labels["Labels"]
        Branch["agent-runtime branch"]
        Actions["GitHub Actions"]
    end

    subgraph AWS["AWS Cloud"]
        subgraph ECS["ECS Fargate Cluster"]
            subgraph OrcContainer["Orchestrator Container"]
                Orch["orchestrator.py"]
                GitHubMCP["GitHub MCP Server"]
                AWSMCP["AWS MCP Server"]
            end
            subgraph WorkContainer["Worker Container"]
                Harness["Worker Harness"]
                Agent["Claude Agent"]
                PlaywrightMCP["Playwright MCP Server"]
            end
        end

        SFN["Step Functions"]
        EFS["EFS Storage"]
        S3["S3 Bucket"]
        CF["CloudFront"]
        CW["CloudWatch"]
        SM["Secrets Manager"]
    end

    subgraph External["External Services"]
        Claude["Claude API"]
    end

    Issues -->|"Approved"| Orch
    Orch <-->|"MCP"| GitHubMCP
    Orch <-->|"MCP"| AWSMCP
    GitHubMCP --> Labels
    AWSMCP --> SFN
    SFN -->|"ECS RunTask"| Harness
    Harness --> Agent
    Agent <-->|"MCP"| PlaywrightMCP
    Agent --> Claude
    Agent -->|"Commit"| Branch
    Agent -->|"Upload"| S3
    S3 --> CF
    Harness --> EFS
    Orch --> CW
    Harness --> CW
    Orch --> SM
    Harness --> SM
    Actions -->|"Deploy"| S3
```

### Harness-Enforced Worker Architecture

The key innovation is the **separation of concerns** between the harness and the agent:

```mermaid
flowchart TB
    subgraph Worker["Worker Container"]
        subgraph HarnessBox["HARNESS (Python) - Workflow Decisions"]
            H1["Setup Environment"]
            H2["Run Smoke Test"]
            H3["Select ONE Test"]
            H4["Build Agent Prompt"]
            H5["Validate Completion"]
            H6["Determine Exit Status"]
        end

        subgraph AgentBox["AGENT (Claude SDK) - Coding Decisions"]
            A1["Read Test Requirements"]
            A2["Implement Feature"]
            A3["Take Screenshot via Playwright MCP"]
            A4["Verify Visually"]
            A5["Mark Test as Pass"]
            A6["Commit Changes"]
        end
    end

    H1 --> H2 --> H3 --> H4
    H4 -->|"Focused prompt"| A1
    A1 --> A2 --> A3 --> A4 --> A5 --> A6
    A6 -->|"Session ends"| H5
    H5 --> H6
```

**Harness Responsibilities:**
- Environment setup (clone, branch, dev servers)
- Smoke testing (fail fast if broken)
- Task selection (ONE test per session)
- Prompt construction (focused, single-task)
- Completion validation (reads feature_list.json)
- Exit status determination (CONTINUE, COMPLETE, FAILED)

**Agent Responsibilities:**
- Technical implementation decisions
- Code quality and visual design
- Tool usage (Playwright MCP for browser automation)
- When to commit

### Orchestrator Container Internals

```mermaid
flowchart TB
    subgraph OrchestratorContainer["Orchestrator Container (orchestrator.py)"]
        subgraph MCPLayer["MCP Server Layer"]
            GitHubMCP["GitHub MCP Server<br/>@modelcontextprotocol/server-github"]
            AWSMCP["AWS MCP Server<br/>@anthropic/mcp-server-aws"]
        end

        subgraph BuiltInTools["Built-in Tools"]
            Heartbeat["publish_heartbeat()<br/>CloudWatch metric"]
            Wait["wait_seconds(n)<br/>Rate limiting"]
        end

        subgraph ClaudeAgent["Claude Agent (Goal-Oriented AI)"]
            SystemPrompt["System Prompt<br/>314 lines of context"]
            Decisions["Intelligent Decisions:<br/>• Issue triage<br/>• Prioritization<br/>• Error handling"]
        end

        subgraph MCPOperations["MCP Operations"]
            ListIssues["mcp__github__list_issues"]
            AddLabel["mcp__github__add_label"]
            PostComment["mcp__github__post_comment"]
            StartExec["mcp__aws__start_execution"]
            DescribeExec["mcp__aws__describe_execution"]
        end
    end

    GitHubMCP --> ListIssues & AddLabel & PostComment
    AWSMCP --> StartExec & DescribeExec
    ClaudeAgent --> MCPOperations
    ClaudeAgent --> BuiltInTools
```

### Worker Container Internals

```mermaid
flowchart TB
    subgraph WorkerContainer["Worker Container (worker_main.py)"]
        subgraph HarnessLayer["Worker Harness (src/worker_harness.py)"]
            subgraph BeforeAgent["BEFORE Agent"]
                Setup["setup_environment()<br/>Clone repo, checkout branch"]
                Servers["start_dev_servers()<br/>Run init.sh, wait ready"]
                Smoke["run_smoke_test()<br/>Playwright health check"]
                Select["select_next_task()<br/>First failing test"]
                BuildPrompt["build_agent_prompt()<br/>Focused single-task"]
            end

            subgraph AfterAgent["AFTER Agent"]
                VerifyCommit["verify_commit_made()<br/>Check git log"]
                CheckStatus["check_test_status()<br/>Read feature_list.json"]
                DetermineExit["determine_exit_status()<br/>CONTINUE/COMPLETE/FAILED"]
                Push["push_changes()<br/>git push origin"]
            end
        end

        subgraph AgentLayer["Claude Agent + MCP"]
            subgraph PlaywrightMCP["Playwright MCP Server<br/>@anthropic/mcp-server-playwright"]
                Screenshot["mcp__playwright__screenshot"]
                Click["mcp__playwright__click"]
                Fill["mcp__playwright__fill"]
                Assert["mcp__playwright__assert_visible"]
            end

            subgraph SDKTools["Claude SDK Tools"]
                Read["Read - View files/screenshots"]
                Write["Write - Create files"]
                Edit["Edit - Modify files"]
                Bash["Bash - Run commands"]
                Glob["Glob - Find files"]
                Grep["Grep - Search content"]
            end

            subgraph SecurityHooks["Security Hooks (src/security.py)"]
                PathHook["Path Validator<br/>Block external paths"]
                BashHook["Bash Allowlist<br/>npm, git, node only"]
                ReadHook["Screenshot Tracker<br/>Track viewed files"]
            end
        end

        subgraph Config["Configuration (src/worker_config.py)"]
            WorkerConfig["WorkerConfig<br/>issue_number, repo, branch"]
            TestTask["TestTask<br/>id, description, steps, status"]
            WorkerStatus["WorkerStatus<br/>CONTINUE=0, COMPLETE=1<br/>FAILED=2, BROKEN_STATE=3"]
        end
    end

    Setup --> Servers --> Smoke --> Select --> BuildPrompt
    BuildPrompt -->|"Focused prompt"| AgentLayer
    AgentLayer -->|"Session ends"| VerifyCommit
    VerifyCommit --> CheckStatus --> DetermineExit --> Push

    SDKTools --> SecurityHooks
```

### Data Flow: Test Implementation

```mermaid
sequenceDiagram
    participant Harness as Worker Harness
    participant Agent as Claude Agent
    participant MCP as Playwright MCP
    participant FS as File System
    participant Git as Git

    Note over Harness: BEFORE Agent
    Harness->>FS: Read feature_list.json
    FS-->>Harness: [{id: "sidebar-v1", passes: false}]
    Harness->>Harness: Select first failing test
    Harness->>Agent: Focused prompt for "sidebar-v1"

    Note over Agent: Agent Session
    Agent->>FS: Read test requirements
    Agent->>FS: Edit src/components/Sidebar.tsx
    Agent->>MCP: screenshot(url, path)
    MCP-->>Agent: Screenshot saved
    Agent->>FS: Read screenshot (verify visually)
    Agent->>FS: Edit feature_list.json (passes: true)
    Agent->>Git: git commit -m "Implement sidebar"

    Note over Harness: AFTER Agent
    Harness->>FS: Read feature_list.json
    FS-->>Harness: [{id: "sidebar-v1", passes: true}]
    Harness->>Harness: Check if all tests pass
    Harness->>Git: git push origin agent-runtime
    Harness->>Harness: Return exit code
```

### Container Responsibilities

```mermaid
flowchart LR
    subgraph Orchestrator["Orchestrator Container"]
        direction TB
        subgraph OTools["MCP Tools"]
            GMCP["GitHub MCP<br/>issues, labels, comments"]
            AMCP["AWS MCP<br/>Step Functions"]
        end
        subgraph OBuiltin["Built-in Tools"]
            HB["publish_heartbeat()"]
            Wait["wait_seconds()"]
        end
        OGoal["Goal-Oriented AI<br/>Intelligent triage<br/>& prioritization"]
    end

    subgraph Worker["Worker Container"]
        direction TB
        subgraph WPhases["Harness Phases"]
            WB["BEFORE: setup, smoke test"]
            WS["SELECT: one failing test"]
            WA["AFTER: validate, push"]
        end
        subgraph WAgent["Agent + MCP"]
            SDK["Claude Agent SDK"]
            PMCP["Playwright MCP<br/>screenshot, click, fill"]
        end
    end

    Orchestrator -->|"Step Functions"| Worker
```

## Issue-to-Build Flow

```mermaid
sequenceDiagram
    participant User
    participant GitHub
    participant Orchestrator
    participant GitHubMCP as GitHub MCP
    participant AWSMCP as AWS MCP
    participant StepFunctions as Step Functions
    participant Harness as Worker Harness
    participant Agent as Claude Agent
    participant PlaywrightMCP as Playwright MCP

    User->>GitHub: Create issue with feature request
    User->>GitHub: Add rocket reaction (approve)

    loop Continuous polling
        Orchestrator->>GitHubMCP: List approved issues
        GitHubMCP-->>Orchestrator: Issue #42 approved
    end

    Orchestrator->>Orchestrator: Triage & prioritize
    Orchestrator->>GitHubMCP: Add agent-building label
    Orchestrator->>GitHubMCP: Post "Build started" comment
    Orchestrator->>AWSMCP: Start Step Functions execution

    AWSMCP->>StepFunctions: StartExecution(issue_number=42)
    StepFunctions->>Harness: ECS RunTask

    Note over Harness: BEFORE Agent
    Harness->>Harness: Clone repo, checkout branch
    Harness->>Harness: Run init.sh (start servers)
    Harness->>Harness: Run smoke test
    Harness->>Harness: Select ONE failing test

    Note over Agent: Agent Session
    Harness->>Agent: Focused single-task prompt

    loop Implementation
        Agent->>Agent: Implement feature
        Agent->>PlaywrightMCP: Take screenshot
        Agent->>Agent: Verify visually
        Agent->>Agent: Mark test as pass
        Agent->>Agent: git commit
    end

    Note over Harness: AFTER Agent
    Harness->>Harness: Verify commit made
    Harness->>Harness: Check feature_list.json status
    Harness->>Harness: Determine exit status
    Harness->>Harness: Push changes

    Harness-->>StepFunctions: Exit code (0/1/2/3)
    StepFunctions-->>Orchestrator: Execution status

    alt All tests pass
        Orchestrator->>GitHubMCP: Remove agent-building label
        Orchestrator->>GitHubMCP: Add agent-complete label
        Orchestrator->>GitHubMCP: Post "Build complete!" comment
    else More tests remain
        Orchestrator->>AWSMCP: Start another worker session
    end
```

## Worker Exit Codes

The harness (not the agent) determines when work is complete:

| Exit Code | Status | Meaning | Next Action |
|-----------|--------|---------|-------------|
| 0 | `CONTINUE` | Test passed, more tests remain | Run another worker session |
| 1 | `COMPLETE` | All tests pass | Mark issue complete |
| 2 | `FAILED` | Unrecoverable error | Stop, post error comment |
| 3 | `BROKEN_STATE` | Smoke test failed | Stop, investigate |

## Worker Build Cycle (Harness-Enforced)

```mermaid
flowchart TD
    Start([Start Worker]) --> Setup["HARNESS: Setup Environment<br/>Clone repo, checkout branch"]
    Setup --> Servers["HARNESS: Start Dev Servers<br/>Run init.sh, wait for ready"]
    Servers --> Smoke{"HARNESS: Smoke Test<br/>App loads correctly?"}

    Smoke -->|Fail| BrokenState([Exit 3: BROKEN_STATE])
    Smoke -->|Pass| SelectTest["HARNESS: Select ONE Feature<br/>First failing feature from feature_list.json"]

    SelectTest --> AnyFailing{"Features remaining?"}
    AnyFailing -->|No| Complete([Exit 1: COMPLETE])
    AnyFailing -->|Yes| BuildPrompt["HARNESS: Build Focused Prompt<br/>Single feature + context"]

    BuildPrompt --> Agent["AGENT: Implement Feature<br/>Technical decisions"]
    Agent --> Screenshot["AGENT: Take Screenshot<br/>via Playwright MCP"]
    Screenshot --> Verify["AGENT: Verify Visually<br/>Read screenshot file"]
    Verify --> MarkPass["AGENT: Mark Feature Pass<br/>Edit feature_list.json"]
    MarkPass --> Commit["AGENT: Commit Changes"]

    Commit --> Validate["HARNESS: Validate Results<br/>Check feature_list.json status"]
    Validate --> TestPassed{"Test now passing?"}

    TestPassed -->|No| RetryCheck{"Retry limit reached?"}
    RetryCheck -->|No| Continue([Exit 0: CONTINUE<br/>Retry same test])
    RetryCheck -->|Yes| Failed([Exit 2: FAILED])

    TestPassed -->|Yes| Push["HARNESS: Push Changes"]
    Push --> AllPass{"All tests pass?"}
    AllPass -->|Yes| Complete
    AllPass -->|No| Continue2([Exit 0: CONTINUE<br/>Next test])
```

## Security Model

```mermaid
flowchart LR
    subgraph Agent["Claude Agent"]
        SDK["Claude Agent SDK"]
        Tools["Tool Calls"]
    end

    subgraph Hooks["Security Hooks (src/security.py)"]
        PathHook["Path Validator<br/>Inside project only"]
        BashHook["Bash Allowlist<br/>npm, git, node, playwright"]
        TestHook["Screenshot Tracker<br/>Must view before marking pass"]
    end

    subgraph Audit["Audit Trail"]
        Log["audit.log"]
    end

    Tools -->|"File ops"| PathHook
    Tools -->|"Commands"| BashHook
    Tools -->|"Read"| TestHook

    PathHook --> Log
    BashHook --> Log
    TestHook --> Log
```

## MCP Server Configuration

### Orchestrator MCP Servers

| Server | Package | Purpose |
|--------|---------|---------|
| GitHub | `@modelcontextprotocol/server-github` | Issue operations, labels, comments |
| AWS | `@anthropic/mcp-server-aws` | Step Functions start/describe |

### Worker MCP Servers

| Server | Package | Purpose |
|--------|---------|---------|
| Playwright | `@anthropic/mcp-server-playwright` | Browser automation, screenshots |

## Component Reference

| Component | File | Description |
|-----------|------|-------------|
| **Orchestrator** | `orchestrator.py` | Long-running ECS service with GitHub/AWS MCP. Goal-oriented AI for intelligent issue triage |
| **Worker Harness** | `src/worker_harness.py` | Python harness enforcing agent workflow constraints |
| **Worker Config** | `src/worker_config.py` | Configuration dataclasses (`WorkerConfig`, `TestTask`, `WorkerStatus`) |
| **Worker Entry** | `worker_main.py` | Harness-based worker entry point |
| **Worker Agent** | `claude_code_agent.py` | Legacy entry point (backward compatibility) |
| **Security Hooks** | `src/security.py` | Path validation, bash allowlist, screenshot tracking |
| **ECS Stack** | `infrastructure/lib/ecs-cluster-stack.ts` | ECS cluster, task definitions |
| **Step Functions** | `infrastructure/lib/step-functions-stack.ts` | Worker invocation state machine |

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run worker directly (legacy mode)
python claude_code_agent.py --project canopy

# Run harness-based worker (requires env vars)
ISSUE_NUMBER=1 GITHUB_REPOSITORY=owner/repo python worker_main.py

# Run with Docker Compose
docker-compose up worker
```

### Environment Variables

```bash
# Required for worker
ISSUE_NUMBER=42
GITHUB_REPOSITORY=owner/repo

# Optional
PROVIDER=anthropic              # or "bedrock"
AGENT_BRANCH=agent-runtime      # git branch
ENVIRONMENT=local               # for secrets lookup
MAX_RETRIES_PER_TEST=3          # retry limit per test
SMOKE_TEST_TIMEOUT=30           # seconds
DEV_SERVER_PORT=6174            # dev server port
```

### Deploy to AWS

```bash
cd infrastructure
npm install
cdk deploy --all
```

## Project Structure

```
├── orchestrator.py              # Orchestrator with GitHub/AWS MCP
├── worker_main.py               # Harness-based worker entry point
├── claude_code_agent.py         # Legacy worker entry point
├── src/
│   ├── worker_harness.py        # Harness enforcing agent constraints
│   ├── worker_config.py         # Worker configuration dataclasses
│   ├── secrets.py               # AWS Secrets Manager utilities
│   ├── github_integration.py    # GitHub API operations
│   ├── security.py              # Security hooks
│   ├── cloudwatch_metrics.py    # Heartbeat metrics
│   └── git_manager.py           # Git operations
├── infrastructure/
│   ├── lib/
│   │   ├── claude-code-stack.ts      # Core infrastructure
│   │   ├── ecs-cluster-stack.ts      # ECS cluster + tasks
│   │   └── step-functions-stack.ts   # Worker state machine
│   └── bin/
│       └── claude-code-infrastructure.ts
├── prompts/
│   ├── system_prompt.txt             # Full system prompt (legacy)
│   ├── worker_system_prompt.txt      # Simplified worker prompt
│   └── canopy/BUILD_PLAN.md          # Project specification
├── Dockerfile.orchestrator      # Orchestrator image (Node.js for MCP)
├── Dockerfile.worker            # Worker image (Node.js for MCP)
└── .github/workflows/
    ├── agent-builder.yml        # Start worker via Step Functions
    ├── stop-agent-on-close.yml  # Cleanup on issue close
    └── deploy-preview.yml       # Deploy to CloudFront
```

## Key Design Principles

1. **Harness responsibility:** Tool access, context management, session structure, state preservation, completion validation
2. **Agent responsibility:** Technical decisions, feature implementation, quality assessment

> The agent makes **coding decisions**. The harness makes **workflow decisions**.

## License

Apache 2.0
