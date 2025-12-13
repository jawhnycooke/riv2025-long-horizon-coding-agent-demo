# Verification Pattern (Screenshot Workflow)

This document explains how the screenshot verification pattern implements the article's recommendation for proving features actually work.

## Article Recommendation

> "Screenshot verification proves the UI actually works"

The article recommends visual verification because:
1. Code compiling doesn't mean UI renders correctly
2. Screenshots prove the feature is visually correct
3. It creates an audit trail of verified features

## Implementation

### Screenshot Directory
```
generated-app/screenshots/
├── T001-homepage.png
├── T002-navigation.png
├── T003-user-profile.png
└── ...
```

### Workflow Overview

```
┌─────────────────┐
│  Implement      │
│  Feature Code   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Start Dev      │
│  Server         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Take Screenshot│
│  with Playwright│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  View Screenshot│
│  (Read tool)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Capture Console│
│  Output         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Verify Visual  │────▶│  Mark Test as   │
│  Correctness    │ OK  │  Passing        │
└────────┬────────┘     └─────────────────┘
         │
         │ FAIL
         ▼
┌─────────────────┐
│  Fix Issues and │
│  Retry          │
└─────────────────┘
```

## Playwright Commands

### Taking Screenshots

```bash
# Basic screenshot
npx playwright screenshot http://localhost:5173 screenshots/T001.png

# Full page screenshot
npx playwright screenshot --full-page http://localhost:5173 screenshots/T001-full.png

# With specific viewport
npx playwright screenshot --viewport-size=1280,720 http://localhost:5173 screenshots/T001.png

# Wait for network idle
npx playwright screenshot --wait-for-timeout=2000 http://localhost:5173 screenshots/T001.png
```

### Capturing Console Output

```bash
# Run Playwright with console capture
npx playwright test --reporter=json > test-results.json

# Or use custom script
node scripts/capture-console.js http://localhost:5173
```

## Security Enforcement

### Track Read Hook

The `track_read_hook` in `src/security.py` enforces the verification flow:

```python
# Simplified from src/security.py
class VerificationTracker:
    def __init__(self):
        self.screenshots_taken: set[str] = set()
        self.screenshots_viewed: set[str] = set()

    def on_screenshot_created(self, path: str) -> None:
        self.screenshots_taken.add(path)

    def on_file_read(self, path: str) -> None:
        if path in self.screenshots_taken:
            self.screenshots_viewed.add(path)

    def can_mark_test_passing(self, test_id: str) -> bool:
        screenshot_path = f"screenshots/{test_id}.png"
        return screenshot_path in self.screenshots_viewed
```

### Blocked Patterns

These attempts to bypass verification are blocked:

```bash
# BLOCKED - Modifying feature_list.json without verification
Edit feature_list.json "passes": false → "passes": true
# Error: Must view screenshot for homepage-renders before marking as passed

# BLOCKED - Bulk status changes
sed -i 's/false/true/g' feature_list.json
# Error: Bulk modification of feature_list.json is not allowed
```

## Worker Verification Task

The Worker agent performs verification:

```python
# Task from Orchestrator
task = """
Verify T001: Homepage renders correctly

Steps:
1. Ensure dev server is running on localhost:5173
2. Take screenshot: npx playwright screenshot http://localhost:5173 screenshots/T001.png
3. View the screenshot using Read tool
4. Check for console errors
5. If visual is correct, update feature_list.json passes to true
6. Update claude-progress.txt with verification result
"""

# Worker executes each step
# Security hooks ensure proper flow
```

## Screenshot Naming Convention

```
screenshots/
├── {TEST_ID}-{description}.png     # Primary verification
├── {TEST_ID}-{description}-full.png # Full page capture
├── {TEST_ID}-{description}-mobile.png # Mobile viewport
└── {TEST_ID}-error-{timestamp}.png # Error state capture
```

Example:
```
screenshots/
├── T001-homepage.png
├── T001-homepage-full.png
├── T001-homepage-mobile.png
├── T002-navigation-open.png
├── T002-navigation-closed.png
└── T003-profile-error-2025-01-15.png
```

## Console Output Verification

Beyond visual verification, console output is checked:

```javascript
// scripts/capture-console.js
const { chromium } = require('playwright');

async function captureConsole(url, outputPath) {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const logs = [];
  page.on('console', msg => logs.push({
    type: msg.type(),
    text: msg.text(),
    timestamp: Date.now()
  }));

  page.on('pageerror', err => logs.push({
    type: 'error',
    text: err.message,
    timestamp: Date.now()
  }));

  await page.goto(url);
  await page.waitForLoadState('networkidle');

  fs.writeFileSync(outputPath, JSON.stringify(logs, null, 2));
  await browser.close();
}
```

## Integration with feature_list.json

When verification passes:

```json
[
  {
    "id": "homepage-renders",
    "description": "Homepage renders correctly",
    "steps": "Navigate to / and verify main content displays",
    "passes": true,
    "retry_count": 0
  }
]
```

## Verification Checklist

For each feature, the agent verifies:

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Visual correctness | Screenshot | Matches expected layout |
| No console errors | Console capture | Zero errors |
| Responsive design | Multiple viewports | Works on mobile/desktop |
| Accessibility | Playwright a11y | No critical violations |
| Performance | Network timing | Loads in < 3 seconds |

## Example: Full Verification Flow

```markdown
## Verifying T005: Settings Page

### 1. Start Dev Server
```bash
npm run dev &
```

### 2. Take Screenshots
```bash
npx playwright screenshot http://localhost:5173/settings screenshots/T005-settings.png
npx playwright screenshot --viewport-size=375,667 http://localhost:5173/settings screenshots/T005-settings-mobile.png
```

### 3. View Screenshots
```
Read: screenshots/T005-settings.png
Read: screenshots/T005-settings-mobile.png
```

### 4. Capture Console
```bash
node scripts/capture-console.js http://localhost:5173/settings logs/T005-console.json
```
```
Read: logs/T005-console.json
```

### 5. Verify Results
- Desktop: Settings form renders correctly ✓
- Mobile: Responsive layout working ✓
- Console: 0 errors, 1 warning (deprecation) ✓

### 6. Update Status
```
Edit feature_list.json: T005 passes false → true
```

### 7. Log Progress
```
Append to claude-progress.txt:
- T005: Settings page - PASSED
  - Screenshots: T005-settings.png, T005-settings-mobile.png
  - Console: 0 errors
```
```

## Benefits

1. **Proof of Work**: Screenshots prove features actually render
2. **Regression Detection**: Can compare screenshots across sessions
3. **Audit Trail**: Timestamped evidence of verification
4. **Visual Debugging**: Screenshots help identify UI issues
5. **Cheating Prevention**: Can't mark tests passed without viewing

## Related Patterns

- [Feature List](./feature-list.md) - feature_list.json structure
- [Progress Tracking](./progress-tracking.md) - Logging verification results
- [Session Recovery](./session-recovery.md) - Git commits after verification
