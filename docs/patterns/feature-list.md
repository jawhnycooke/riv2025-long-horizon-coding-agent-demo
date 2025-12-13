# Feature List Pattern (feature_list.json)

This document explains how the `feature_list.json` pattern implements the article's recommendation for tracking feature status.

## Article Recommendation

> "Using JSON for feature_list.json adds friction that discourages the model from bulk-editing feature statuses"

The article recommends using a JSON-based feature list because:
1. JSON requires precise syntax (commas, quotes, brackets)
2. Editing individual entries is more deliberate than bulk operations
3. It's machine-readable for automated verification

## Implementation

### File Location
```
generated-app/feature_list.json
```

### Schema

```json
[
  {
    "id": "homepage-renders",
    "description": "The homepage should display the main content",
    "steps": "Navigate to / and verify main content displays",
    "passes": false,
    "retry_count": 0
  }
]
```

### Status Field

| Field | Type | Meaning |
|-------|------|---------|
| `passes` | `boolean` | `false` = not yet passing, `true` = verified with screenshot |
| `retry_count` | `number` | Number of implementation attempts |

## Security Controls

### Bulk Modification Prevention

The agent cannot bulk-modify `feature_list.json` using shell commands. These are blocked:

```bash
# BLOCKED - Would allow cheating
sed -i 's/false/true/g' feature_list.json
awk '{gsub(/false/,"true")}1' feature_list.json
jq '.[].passes = true' feature_list.json
python -c "import json; ..." feature_list.json
```

### Required Verification Flow

To mark a feature as passing, the agent must:

1. **Take a screenshot** of the feature
   ```bash
   npx playwright screenshot http://localhost:5173 screenshots/homepage-renders.png
   ```

2. **View the screenshot** via Read tool
   ```
   Read: screenshots/homepage-renders.png
   ```

3. **Edit the specific feature** via Edit tool
   ```json
   // Only then can Edit tool modify:
   "passes": false → "passes": true
   ```

This is enforced by `track_read_hook` in `src/security.py`.

## Implementation Details

### Creating feature_list.json

The harness generates `feature_list.json` on first run from BUILD_PLAN.md:

```python
# From worker_harness.py
def ensure_feature_list_exists(self) -> bool:
    """Generate feature_list.json if it doesn't exist."""
    if self.config.feature_list_path.exists():
        return True
    return self._run_initialization_agent()
```

### Updating Feature Status

The Worker agent updates features via the Edit tool:

```python
# Worker receives task from Harness
task = "Implement homepage-renders: Homepage renders correctly"

# Worker takes screenshot
# Worker views screenshot
# Worker edits feature_list.json
Edit(
    file_path="generated-app/feature_list.json",
    old_string='"id": "homepage-renders",\n    "passes": false',
    new_string='"id": "homepage-renders",\n    "passes": true'
)
```

### Reading Progress

The Harness reads `feature_list.json` to select next task:

```python
def get_pending_features(feature_list: list[dict]) -> list[dict]:
    return [
        feature for feature in feature_list
        if not feature.get("passes", False)
    ]
```

## Integration with Progress Tracking

When a feature passes, the agent also updates `claude-progress.txt`:

```
## Feature Verification
- homepage-renders: Homepage renders correctly - PASSED (screenshot: screenshots/homepage-renders.png)
```

This creates a chronological record alongside the structured JSON.

## Benefits

1. **Cheating Prevention**: JSON friction + security hooks prevent bulk modifications
2. **Machine Readable**: Automated tools can parse progress
3. **Audit Trail**: Each modification is tracked via Edit tool
4. **Visual Verification**: Screenshot requirement proves UI works
5. **Simple Boolean**: `passes: true/false` is clearer than string status values

## Related Patterns

- [Progress Tracking](./progress-tracking.md) - Chronological log format
- [Verification](./verification.md) - Screenshot workflow details
- [Session Recovery](./session-recovery.md) - Using feature_list.json for recovery
