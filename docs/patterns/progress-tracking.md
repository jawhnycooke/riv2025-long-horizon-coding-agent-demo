# Progress Tracking Pattern (claude-progress.txt)

This document explains how the `claude-progress.txt` pattern implements the article's recommendation for maintaining session context.

## Article Recommendation

> "claude-progress.txt files documenting previous work"

The article recommends a chronological log because:
1. It preserves context across session boundaries
2. New sessions can quickly understand what was done
3. It captures reasoning, not just actions

## Implementation

### File Location
```
generated-app/claude-progress.txt
```

### Format

```markdown
# Claude Progress Log

## Session 1 - 2025-01-15T10:00:00Z

### Context Recovery
- Read feature_list.json: 10 features pending
- Read git log: Initial commit
- Selected feature: T001 - Homepage

### Work Performed
- Created src/App.tsx with main layout
- Added Tailwind CSS configuration
- Implemented responsive header component

### Verification
- T001: Homepage renders correctly - PASSED
  - Screenshot: screenshots/T001.png
  - Console: No errors

### State at End
- feature_list.json: 1 passed, 9 pending
- Last commit: abc1234 "feat: add homepage layout"
- Next recommended: T002 - Navigation menu

---

## Session 2 - 2025-01-15T14:00:00Z

### Context Recovery
- Read feature_list.json: 1 passed, 9 pending
- Read claude-progress.txt: Session 1 completed homepage-renders
- Selected feature: T002 - Navigation menu
...
```

## Key Sections

### Context Recovery

Documents what the agent read at session start:

```markdown
### Context Recovery
- Read feature_list.json: X passed, Y pending
- Read git log: [recent commits]
- Read claude-progress.txt: [summary of previous session]
- Selected feature: [next feature to implement]
```

This creates a traceable record of the agent's decision-making.

### Work Performed

Documents actual changes made:

```markdown
### Work Performed
- [Action 1]: [Details]
- [Action 2]: [Details]
- Commits: [commit hashes with messages]
```

### Verification

Documents test verification:

```markdown
### Verification
- [Test ID]: [Test name] - [STATUS]
  - Screenshot: [path]
  - Console: [summary]
  - Notes: [any observations]
```

### State at End

Documents the session ending state:

```markdown
### State at End
- feature_list.json: X passed, Y pending
- Last commit: [hash] "[message]"
- Next recommended: [suggestion for next session]
- Blockers: [any issues encountered]
```

## Writing Progress

The agent writes progress updates throughout the session:

```python
# Worker appends to progress file
def log_progress(message: str, generation_dir: Path) -> None:
    progress_file = generation_dir / "claude-progress.txt"
    timestamp = datetime.now().isoformat()

    with open(progress_file, "a") as f:
        f.write(f"\n{timestamp}: {message}")
```

## Reading Progress

The Orchestrator reads progress at session start:

```python
def read_progress(generation_dir: Path) -> str:
    progress_file = generation_dir / "claude-progress.txt"
    if progress_file.exists():
        return progress_file.read_text()
    return ""
```

## Integration with Session Recovery

The progress file works with git commits:

```
Session N ends:
  1. Write "State at End" section
  2. Git commit with meaningful message
  3. Git push to remote

Session N+1 starts:
  1. Read claude-progress.txt (last session summary)
  2. Read git log (verify commits)
  3. Read tests.json (current status)
  4. Select next feature
```

## Best Practices

### DO

- Write progress incrementally (not at end)
- Include specific file paths and commit hashes
- Document decisions and reasoning
- Note any blockers or issues

### DON'T

- Overwrite previous session entries
- Include sensitive information
- Make entries too verbose
- Skip the context recovery section

## Example: Full Session Entry

```markdown
## Session 3 - 2025-01-16T09:30:00Z

### Context Recovery
- feature_list.json: 4 passed, 6 pending
- Previous session: Completed T004 (user profile page)
- Git log shows: 12 commits, last was "fix: profile avatar loading"
- Selected: T005 - Settings page

### Work Performed
- Created src/pages/Settings.tsx
- Added form validation with react-hook-form
- Implemented theme toggle (dark/light mode)
- Fixed accessibility issues (aria labels)

### Commits
- def4567: "feat: add settings page structure"
- ghi7890: "feat: implement theme toggle"
- jkl0123: "fix: accessibility improvements"

### Verification
- T005: Settings page - PASSED
  - Screenshot: screenshots/T005.png
  - Console: No errors
  - Accessibility: All WCAG checks pass

### State at End
- feature_list.json: 5 passed, 5 pending
- Last commit: jkl0123 "fix: accessibility improvements"
- Next recommended: T006 - Dashboard analytics
- Notes: Consider adding unit tests for Settings form

---
```

## Benefits

1. **Context Continuity**: New sessions start with full context
2. **Debugging**: Can trace back through session history
3. **Accountability**: Clear record of what was done and why
4. **Recovery**: If something breaks, can identify when/how

## Related Patterns

- [Feature List](./feature-list.md) - Structured test status
- [Session Recovery](./session-recovery.md) - Git-based recovery
- [Verification](./verification.md) - Screenshot workflow
