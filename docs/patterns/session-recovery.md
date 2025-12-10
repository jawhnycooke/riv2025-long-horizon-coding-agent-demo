# Session Recovery Pattern

This document explains how the session recovery pattern implements the article's recommendation for maintaining agent state across sessions and enabling recovery from failures.

## Article Recommendation

> "Git commits serve as recovery points... the agent can reset to a known good state"

The article recommends using git commits as recovery checkpoints because:
1. Each commit represents a verified working state
2. The agent can roll back if something breaks
3. Remote push ensures durability across container restarts

## Implementation

### Components

| Component | Purpose | File |
|-----------|---------|------|
| State Machine | Track agent state | `agent_state.json` |
| Git Manager | Commit and push changes | `src/git_manager.py` |
| Progress Log | Session history | `claude-progress.txt` |
| Tests JSON | Feature status | `tests.json` |

## State Machine

### File Location
```
generated-app/agent_state.json
```

### Schema

```json
{
  "desired_state": "continuous",
  "current_state": "continuous",
  "timestamp": "2025-01-15T23:52:09.505Z",
  "setBy": "agent",
  "note": "Running in continuous mode",
  "build_plan_version": "1.0.0",
  "session_id": "abc123",
  "recovery_point": {
    "commit": "def456",
    "tests_passed": 5,
    "last_feature": "T005"
  }
}
```

### States

| State | Meaning | Transitions |
|-------|---------|-------------|
| `continuous` | Normal operation | → `pause`, `terminated` |
| `run_once` | Execute one task then pause | → `pause` |
| `run_cleanup` | Technical debt cleanup | → `pause` |
| `pause` | Waiting for next session | → `continuous` |
| `terminated` | Session complete | Terminal |

### State Transitions

```
                    ┌──────────────┐
                    │  continuous  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌──────────┐  ┌───────────┐
        │run_once │  │run_cleanup│  │  pause    │
        └────┬────┘  └─────┬────┘  └───────────┘
             │             │            ▲
             └─────────────┴────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  terminated  │
                    └──────────────┘
```

## Git Recovery Points

### Auto-Commit Strategy

The agent commits after each verified feature:

```python
# From git_manager.py
def create_recovery_point(generation_dir: Path, feature_id: str) -> str:
    """Create a git commit as a recovery checkpoint."""
    # Stage all changes
    subprocess.run(["git", "add", "-A"], cwd=generation_dir)

    # Commit with meaningful message
    message = f"feat({feature_id}): verified and passing"
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=generation_dir,
        capture_output=True
    )

    # Push to remote for durability
    subprocess.run(["git", "push"], cwd=generation_dir)

    # Return commit hash
    return get_current_commit_hash(generation_dir)
```

### Recovery Process

If something goes wrong:

```python
def recover_to_last_good_state(generation_dir: Path) -> None:
    """Reset to the last verified commit."""
    # Read state to find last good commit
    state = read_agent_state(generation_dir)
    recovery_commit = state.get("recovery_point", {}).get("commit")

    if recovery_commit:
        # Hard reset to that commit
        subprocess.run(
            ["git", "reset", "--hard", recovery_commit],
            cwd=generation_dir
        )

        # Log the recovery
        log_progress(f"Recovered to commit {recovery_commit}")
```

## Session Startup Sequence

From the article's recommendations:

```python
def session_startup(generation_dir: Path) -> dict:
    """Execute the recommended startup sequence."""
    context = {}

    # 1. Confirm directory
    assert Path.cwd() == generation_dir, "Wrong directory!"

    # 2. Read progress files
    context["progress"] = read_file(generation_dir / "claude-progress.txt")
    context["tests"] = read_json(generation_dir / "tests.json")
    context["state"] = read_json(generation_dir / "agent_state.json")

    # 3. Check git history
    context["git_log"] = get_recent_commits(generation_dir, count=10)
    context["git_status"] = get_git_status(generation_dir)

    # 4. Select next feature
    pending = [t for t in context["tests"]["tests"] if t["status"] == "pending"]
    context["next_feature"] = pending[0] if pending else None

    # 5. Run init script (if exists)
    init_script = generation_dir / "init.sh"
    if init_script.exists():
        subprocess.run(["bash", str(init_script)], cwd=generation_dir)

    # 6. Verify baseline
    run_e2e_tests(generation_dir, verify_only=True)

    return context
```

## Orchestrator Prompt Integration

The orchestrator system prompt includes recovery instructions:

```markdown
## Session Recovery

At the start of each session:

1. Run `pwd` to confirm you're in the correct directory
2. Read these files to understand current state:
   - `tests.json` - Which features are done/pending
   - `claude-progress.txt` - What happened in previous sessions
   - `agent_state.json` - Current state machine status
3. Run `git log --oneline -10` to see recent commits
4. Select the highest-priority pending feature
5. If `init.sh` exists, run it to start the dev server
6. Run existing E2E tests to verify baseline before making changes

If you encounter an unrecoverable error:
1. Document the issue in claude-progress.txt
2. Commit the current state with message "WIP: [issue description]"
3. Update agent_state.json to "pause" state
4. The next session will pick up from this point
```

## CloudWatch Heartbeat

For long-running sessions, a heartbeat ensures session health:

```python
# From cloudwatch_metrics.py
def publish_heartbeat(session_id: str) -> None:
    """Publish heartbeat metric to CloudWatch."""
    cloudwatch.put_metric_data(
        Namespace="AgentCore",
        MetricData=[{
            "MetricName": "SessionHeartbeat",
            "Value": 1,
            "Unit": "Count",
            "Dimensions": [
                {"Name": "SessionId", "Value": session_id}
            ]
        }]
    )
```

The issue-poller workflow checks heartbeat staleness:

```yaml
# From issue-poller.yml
- name: Check session health
  run: |
    LAST_HEARTBEAT=$(aws cloudwatch get-metric-statistics ...)
    if [ $STALENESS -gt $THRESHOLD ]; then
      echo "Session unhealthy, triggering recovery"
    fi
```

## Benefits

1. **Durability**: Git commits survive container restarts
2. **Rollback**: Can recover from failed features
3. **Continuity**: New sessions resume from last state
4. **Visibility**: Git history shows progress over time
5. **Debugging**: Can checkout any point in history

## Example: Full Recovery Scenario

```
Session 5 crashes during T008 implementation:

1. Container dies unexpectedly
2. Last commit was T007 (verified passing)
3. agent_state.json shows:
   - current_state: "continuous"
   - recovery_point.commit: "abc123" (T007)

Session 6 starts:

1. Read agent_state.json → see recovery_point
2. Run `git status` → see uncommitted changes
3. Decision: Discard partial T008 work
4. Run `git reset --hard abc123`
5. Continue from T008 fresh
6. Log in claude-progress.txt: "Recovered from crash, restarting T008"
```

## Related Patterns

- [Feature List](./feature-list.md) - tests.json for status tracking
- [Progress Tracking](./progress-tracking.md) - Chronological log
- [Verification](./verification.md) - Screenshot workflow
