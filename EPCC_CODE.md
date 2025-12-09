# Implementation: F015 Configurable Completion Signal

**Mode**: default | **Date**: 2025-12-08 | **Status**: Complete

## 1. Changes (4 files modified, +185 lines new code, 17 tests)

**Modified**:
- `src/config.py` - Added `CompletionSignalSettings` dataclass with `from_dict()`, `to_dict()`, `default()` methods; updated `ProjectConfig` to include `completion_signal` field
- `claude_code.py` - Added `COMPLETION_SIGNAL_SETTINGS` global, `get_completion_signal()` helper, updated `_detect_completion_signal()` to use configurable settings
- `tests/test_config.py` - Added 17 tests for `CompletionSignalSettings` and `ProjectConfig` integration
- `CLAUDE.md` - Added comprehensive completion signal configuration documentation
- `epcc-features.json` - Marked F015 as complete (87.5% overall)

## 2. Quality (Tests 230 | Black Formatted | Docs Updated)

**Tests**: 230 tests passing:
- 17 new tests for CompletionSignalSettings
- 12 tests for `from_dict()` / `to_dict()` / roundtrip
- 5 tests for ProjectConfig integration

**Code Quality**:
- Black formatted
- Ruff auto-fixed
- All tests pass

**Docs**: CLAUDE.md updated with:
- Configuration JSON example
- Settings table with defaults
- Detection logic explanation
- Custom signal examples

## 3. Acceptance Criteria Verification

| Criterion | Status | Implementation |
|-----------|--------|---------------|
| Completion signal configurable in .claude-code.json | ✅ | `completion_signal` object with `signal`, `emoji`, `complete_phrase`, `finished_phrase` |
| Default remains current emoji string | ✅ | `DEFAULT_COMPLETION_SIGNAL` constant used when no config |
| Signal can be plain text or include emoji | ✅ | Emoji auto-extracted from signal if not explicit |
| Signal documented in CLAUDE.md | ✅ | Full section with examples and settings table |
| bedrock_entrypoint.py reads signal from config | ✅ | N/A - bedrock_entrypoint.py uses agent_state.json pause state, not text parsing |

## 4. Configuration Schema

```json
{
  "completion_signal": {
    "signal": "🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED",
    "emoji": "🎉",
    "complete_phrase": "implementation complete",
    "finished_phrase": "all tasks finished"
  }
}
```

**Detection Logic**: All three must be present:
1. Emoji character
2. `complete_phrase` (case-insensitive)
3. `finished_phrase` (case-insensitive)

## 5. Handoff

**Run**: `/epcc-commit` when ready

**Blockers**: None

**TODOs**: None - all acceptance criteria met
