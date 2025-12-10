# Product Requirement Document: Claude Agent SDK Modernization

**Created**: 2025-12-10
**Version**: 1.0
**Status**: Draft
**Complexity**: Complex

---

## Executive Summary

Modernize the long-horizon coding agent to fully leverage the Claude Agent SDK capabilities, implementing an orchestrator pattern with specialized subagents, SDK-native sandbox security, structured outputs, and programmatic agent definitions. This enables parallel task execution, better reliability, and standardized outputs while maintaining the existing ECS Fargate deployment model.

## Problem Statement

The current implementation uses the Claude Agent SDK but only leverages basic features:
- Single monolithic agent handles all tasks sequentially
- Custom hook-based security instead of SDK sandbox
- No structured output validation
- Agents defined implicitly in prompts rather than programmatically
- No parallel execution capability for independent tasks

This limits throughput, makes the agent harder to extend, and doesn't take advantage of the SDK's full power.

## Target Users

### Primary Users
- **DevOps/Platform Engineers**: Deploy and operate the agent infrastructure
- **Developers**: Use the agent to build React applications from GitHub issues
- **Agent Maintainers**: Extend and customize agent behavior

### Pain Points
- Long build times due to sequential task execution
- Difficult to add new agent capabilities
- Inconsistent output formats for test results and progress reports
- Security model is custom code rather than SDK-managed

## Goals & Success Criteria

### Product Goals
1. Reduce average build time by 30%+ through parallel subagent execution
2. Standardize all agent outputs with JSON schema validation
3. Simplify security model by migrating to SDK sandbox
4. Enable easy addition of new specialized agents

### Success Metrics
- Build completion time (target: 30% reduction)
- Agent reliability (target: 95%+ successful completions)
- Code maintainability (target: 50% reduction in custom security code)

### Acceptance Criteria
- [ ] Orchestrator agent coordinates 4+ specialized subagents
- [ ] All subagents defined programmatically via `AgentDefinition`
- [ ] SDK sandbox replaces custom bash security hooks
- [ ] Test results, progress reports, and build artifacts use structured outputs
- [ ] Existing ECS Fargate deployment continues working

## Core Features

### Must Have (P0 - MVP)

#### 1. Orchestrator Architecture
**What**: Main agent that delegates work to specialized subagents
**Why**: Enables parallel execution and separation of concerns
**Components**:
- Orchestrator agent (coordinates workflow)
- Research subagent (codebase exploration, documentation lookup)
- File operations subagent (bulk file creation, refactoring)
- Testing subagent (test execution, screenshot verification)
- Code review subagent (security, style, best practices)

#### 2. Programmatic Agent Definitions
**What**: Define all agents in Python code using `AgentDefinition`
**Why**: Better control, type safety, easier testing than markdown files
**Implementation**:
```python
agents={
    "research": AgentDefinition(
        description="Explores codebase and gathers context",
        prompt="You are a research agent...",
        tools=["Read", "Glob", "Grep", "WebSearch"],
        model="haiku"  # Fast model for research
    ),
    "file-ops": AgentDefinition(
        description="Handles bulk file operations",
        prompt="You are a file operations agent...",
        tools=["Read", "Write", "Edit", "MultiEdit"],
        model="sonnet"
    ),
    # ... more agents
}
```

#### 3. SDK Sandbox Security
**What**: Migrate from custom hooks to `SandboxSettings`
**Why**: SDK-managed security is more robust and maintainable
**Configuration**:
```python
sandbox=SandboxSettings(
    enabled=True,
    autoAllowBashIfSandboxed=True,
    excludedCommands=["docker"],
    network=SandboxNetworkConfig(
        allowLocalBinding=True,  # For dev servers
        allowUnixSockets=["/var/run/docker.sock"]
    )
)
```

#### 4. Structured Output Schemas
**What**: JSON schema validation for agent outputs
**Why**: Consistent, parseable outputs for automation
**Schemas needed**:
- **Test Results**: `{passed: bool, tests: [{name, status, screenshot?, error?}], summary}`
- **Progress Reports**: `{phase, completedTasks, remainingTasks, blockers?, metrics}`
- **Build Artifacts**: `{files: [{path, type, size}], metadata, deploymentConfig}`

### Should Have (P1)

#### 5. Parallel Subagent Execution
**What**: Run independent subagents concurrently
**Why**: Faster builds when tasks don't depend on each other
**Example**: Research + Code Review can run in parallel during initial analysis

#### 6. Enhanced MCP Server Integration
**What**: Add custom MCP servers for specialized tooling
**Why**: Extend agent capabilities without modifying core code
**Potential servers**:
- GitHub MCP (enhanced issue/PR management)
- Playwright MCP (direct browser control)
- Database MCP (if persistent storage needed)

### Nice to Have (P2)

#### 7. Agent Metrics & Observability
**What**: Structured telemetry for subagent performance
**Why**: Optimize agent allocation and identify bottlenecks

#### 8. Dynamic Agent Scaling
**What**: Spawn additional subagents based on workload
**Why**: Handle complex projects with many files/tests

## User Journeys

### Primary Journey: Building a React App from GitHub Issue

1. **GitHub issue approved** with 🚀 reaction
2. **Orchestrator agent starts**, reads issue requirements
3. **Research subagent** explores similar code patterns, gathers context
4. **Orchestrator plans** implementation based on research
5. **File operations subagent** creates initial file structure (parallel with step 6)
6. **Code review subagent** validates architecture decisions
7. **Orchestrator implements** core features
8. **Testing subagent** runs E2E tests, captures screenshots
9. **Orchestrator iterates** based on test failures
10. **Build artifacts output** with structured metadata
11. **Progress report posted** to GitHub issue

### Secondary Journey: Cleanup Session

1. **Cleanup mode triggered** via state file
2. **Orchestrator delegates** to specialized cleanup subagent
3. **Code review subagent** identifies technical debt
4. **File operations subagent** performs refactoring
5. **Testing subagent** verifies no regressions
6. **Structured report** of changes made

## Technical Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                        │
│  (Coordinates workflow, makes high-level decisions)          │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        │             │             │             │
        ▼             ▼             ▼             ▼
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│  Research │ │ File Ops  │ │  Testing  │ │Code Review│
│  Subagent │ │ Subagent  │ │ Subagent  │ │ Subagent  │
│  (haiku)  │ │ (sonnet)  │ │ (sonnet)  │ │  (haiku)  │
└───────────┘ └───────────┘ └───────────┘ └───────────┘
     │             │             │             │
     └─────────────┴─────────────┴─────────────┘
                      │
              ┌───────┴───────┐
              │  SDK Sandbox  │
              │  (Security)   │
              └───────────────┘
```

### Technology Stack
- **Runtime**: Python 3.11+ with Claude Agent SDK
- **Agent SDK**: `claude-agent-sdk` (latest)
- **Deployment**: ECS Fargate (unchanged)
- **Provider**: Anthropic API or Amazon Bedrock (configurable)

### Key Implementation Files
- `agent.py` - Orchestrator agent with subagent definitions
- `src/agents/` - New directory for subagent-specific logic
- `src/schemas/` - JSON schemas for structured outputs
- `src/sandbox.py` - SDK sandbox configuration

### Migration Strategy
1. Keep existing `SecurityValidator` hooks during transition
2. Add SDK sandbox alongside hooks
3. Validate both produce same security outcomes
4. Remove custom hooks once SDK sandbox proven

## Constraints

### Timeline
- **MVP**: Core orchestrator + 2 subagents (Research, Testing)
- **Phase 2**: Add File Ops + Code Review subagents
- **Phase 3**: Structured outputs + parallel execution

### Technical Constraints
- Must maintain backward compatibility with existing GitHub workflow
- ECS Fargate deployment model unchanged
- Support both Anthropic and Bedrock providers

### Security/Compliance
- SDK sandbox must provide equivalent or better security than current hooks
- All file operations restricted to project directory
- Network access limited to required domains

## Out of Scope

- Migrating away from ECS Fargate to AgentCore-managed deployment
- Real-time streaming UI for agent progress
- Multi-project concurrent execution
- Custom model fine-tuning

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| SDK sandbox behavior differs from current hooks | High | Run both in parallel during migration, compare outcomes |
| Subagent coordination complexity | Medium | Start with simple orchestrator, add complexity incrementally |
| Increased token usage from multiple agents | Medium | Use haiku for simple tasks, monitor costs closely |
| Bedrock compatibility with new SDK features | Medium | Test all features on both providers early |

## Open Questions

1. Should subagents share a conversation context or be fully isolated?
2. What's the optimal model allocation (opus/sonnet/haiku) per subagent type?
3. How should subagent failures be handled - retry, escalate to orchestrator, or fail build?

## Dependencies

- Claude Agent SDK v0.1.x+ (for programmatic agents, sandbox)
- Existing ECS/Fargate infrastructure
- GitHub Actions workflows (unchanged)

## Next Steps

This PRD feeds into the EPCC workflow. Since this is a **brownfield project** (existing codebase):

1. **Review & approve** this PRD
2. Run `/epcc-explore` to understand existing agent architecture deeply
3. Run `/epcc-plan` to create detailed implementation plan
4. Begin development with `/epcc-code`
5. Finalize with `/epcc-commit`

---

**End of PRD**
