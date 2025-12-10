# Feature List Pattern (tests.json)

This document explains how the `tests.json` pattern implements the article's recommendation for tracking feature status.

## Article Recommendation

> "Using JSON for tests.json adds friction that discourages the model from bulk-editing test statuses"

The article recommends using a JSON-based feature list because:
1. JSON requires precise syntax (commas, quotes, brackets)
2. Editing individual entries is more deliberate than bulk operations
3. It's machine-readable for automated verification

## Implementation

### File Location
```
generated-app/tests.json
```

### Schema

```json
{
  "tests": [
    {
      "id": "T001",
      "name": "Homepage renders correctly",
      "description": "The homepage should display the main content",
      "status": "pending",
      "screenshot": null,
      "verifiedAt": null
    }
  ],
  "metadata": {
    "totalTests": 10,
    "passed": 3,
    "failed": 0,
    "pending": 7
  }
}
```

### Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Test not yet attempted |
| `passed` | Test verified with screenshot |
| `failed` | Test attempted but failed |
| `blocked` | Test blocked by dependency |

## Security Controls

### Bulk Modification Prevention

The agent cannot bulk-modify `tests.json` using shell commands. These are blocked:

```bash
# BLOCKED - Would allow cheating
sed -i 's/pending/passed/g' tests.json
awk '{gsub(/pending/,"passed")}1' tests.json
jq '.tests[].status = "passed"' tests.json
python -c "import json; ..." tests.json
```

### Required Verification Flow

To mark a test as passing, the agent must:

1. **Take a screenshot** of the feature
   ```bash
   npx playwright screenshot http://localhost:5173 screenshots/T001.png
   ```

2. **View the screenshot** via Read tool
   ```
   Read: screenshots/T001.png
   ```

3. **Edit the specific test** via Edit tool
   ```json
   // Only then can Edit tool modify:
   "status": "pending" → "status": "passed"
   ```

This is enforced by `track_read_hook` in `src/security.py`.

## Implementation Details

### Creating tests.json

The orchestrator creates `tests.json` during session initialization:

```python
# From session_manager.py
def create_tests_json(features: list[dict]) -> dict:
    return {
        "tests": [
            {
                "id": f"T{i:03d}",
                "name": feature["name"],
                "description": feature["description"],
                "status": "pending",
                "screenshot": None,
                "verifiedAt": None,
            }
            for i, feature in enumerate(features, 1)
        ],
        "metadata": {
            "totalTests": len(features),
            "passed": 0,
            "failed": 0,
            "pending": len(features),
        },
    }
```

### Updating Test Status

The Worker agent updates tests via the Edit tool:

```python
# Worker receives task from Orchestrator
task = "Verify T001: Homepage renders correctly"

# Worker takes screenshot
# Worker views screenshot
# Worker edits tests.json
Edit(
    file_path="generated-app/tests.json",
    old_string='"id": "T001",\n      "status": "pending"',
    new_string='"id": "T001",\n      "status": "passed"'
)
```

### Reading Progress

The Orchestrator reads `tests.json` at session start:

```python
def get_pending_tests(tests_json: dict) -> list[dict]:
    return [
        test for test in tests_json["tests"]
        if test["status"] == "pending"
    ]
```

## Integration with Progress Tracking

When a test passes, the agent also updates `claude-progress.txt`:

```
## Test Verification
- T001: Homepage renders correctly - PASSED (screenshot: screenshots/T001.png)
```

This creates a chronological record alongside the structured JSON.

## Benefits

1. **Cheating Prevention**: JSON friction + security hooks prevent bulk modifications
2. **Machine Readable**: Automated tools can parse progress
3. **Audit Trail**: Each modification is tracked via Edit tool
4. **Visual Verification**: Screenshot requirement proves UI works

## Related Patterns

- [Progress Tracking](./progress-tracking.md) - Chronological log format
- [Verification](./verification.md) - Screenshot workflow details
- [Session Recovery](./session-recovery.md) - Using tests.json for recovery
