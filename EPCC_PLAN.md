# Plan: Claude Code Agent Enhancements

**Created**: 2025-12-03 | **Effort**: ~32h | **Complexity**: Medium

## 1. Objective

**Goal**: Enhance the Claude Code agent with testing, type safety, reliability, observability, and developer experience improvements.

**Why**: Code review identified gaps in test coverage, type safety, error handling, and developer tooling that reduce reliability and maintainability.

**Success Criteria**:
- All 16 features implemented and verified
- Test coverage >60% on core modules
- mypy strict passes on all files
- Pre-commit hooks enforce quality on every commit

---

## 2. Approach

**Strategy**: Phased rollout starting with quick wins, then quality gates, then core features.

**From TECH_REQ.md**:
- pytest + pytest-cov for testing
- mypy strict with gradual adoption
- black + ruff via pre-commit
- Custom retry decorator with exponential backoff
- JSONL audit logs with rotation
- OpenTelemetry for tracing (already imported)

**Key Dependencies**:
```
F016 (Version) → F014 (Validate) uses version
F013 (Pre-commit) → F002 (mypy) needs pre-commit configured
F001 (Tests) → F003, F004 need test coverage
F005 (AWS Profile) → F014 (Validate) needs profile for credential check
```

---

## 3. Tasks

### Phase 1: Quick Wins (~3h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 1.1 | **F016: Add --version flag** | 1h | None | L |
|     | - Add `__version__` to src/__init__.py | | | |
|     | - Add argparse --version action | | | |
|     | - Show config path, provider, model | | | |
| 1.2 | **F014: Add --validate flag** | 2h | None | L |
|     | - Add argparse --validate action | | | |
|     | - Validate .claude-code.json exists | | | |
|     | - Validate BUILD_PLAN.md exists | | | |
|     | - Validate AWS credentials (Bedrock) | | | |
|     | - Validate ANTHROPIC_API_KEY (Anthropic) | | | |

### Phase 2: Quality Gates (~6h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 2.1 | **Create pyproject.toml** | 1h | None | L |
|     | - Project metadata | | | |
|     | - pytest config | | | |
|     | - mypy config (strict with overrides) | | | |
|     | - black + ruff config | | | |
| 2.2 | **F013: Pre-commit hooks** | 1.5h | 2.1 | L |
|     | - Create .pre-commit-config.yaml | | | |
|     | - Configure black, ruff, mypy hooks | | | |
|     | - Add pre-commit to requirements-dev.txt | | | |
|     | - Document installation in README | | | |
| 2.3 | **F002: Type hints - src/config.py** | 1h | 2.1 | L |
|     | - Add missing type hints | | | |
|     | - Verify mypy --strict passes | | | |
| 2.4 | **F002: Type hints - src/security.py** | 1.5h | 2.3 | M |
|     | - Add type hints to hook functions | | | |
|     | - Handle complex callback types | | | |
| 2.5 | **F002: Type hints - remaining modules** | 1h | 2.4 | L |
|     | - token_tracker, logging_utils, etc. | | | |

### Phase 3: Test Infrastructure (~5h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 3.1 | **F001: Test setup** | 1h | 2.1 | L |
|     | - Create tests/ directory | | | |
|     | - Create conftest.py with fixtures | | | |
|     | - Add pytest deps to requirements-dev.txt | | | |
| 3.2 | **F001: test_config.py** | 1.5h | 3.1 | L |
|     | - Test config loading | | | |
|     | - Test provider detection | | | |
|     | - Test ProjectConfig.from_dict | | | |
| 3.3 | **F001: test_security.py** | 2h | 3.1 | M |
|     | - Test path validation hooks | | | |
|     | - Test bash command allowlist | | | |
|     | - Test blocked patterns | | | |
| 3.4 | **Verify coverage >60%** | 0.5h | 3.2, 3.3 | L |

### Phase 4: Security - Audit Trail (~4h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 4.1 | **F004: Create src/audit.py** | 2h | None | L |
|     | - AuditLogger class | | | |
|     | - JSONL format with timestamps | | | |
|     | - RotatingFileHandler (10MB, 5 backups) | | | |
|     | - Event types: bash_command, bash_blocked, file_read, file_write, file_blocked | | | |
| 4.2 | **F004: Integrate into security.py** | 1.5h | 4.1 | M |
|     | - Log all bash commands | | | |
|     | - Log blocked commands with reason | | | |
|     | - Log file operations | | | |
| 4.3 | **F004: Write test_audit.py** | 0.5h | 4.1, 3.1 | L |

### Phase 5: Reliability - Retry Logic (~3h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 5.1 | **F003: Create src/retry.py** | 1.5h | None | L |
|     | - RetryConfig dataclass | | | |
|     | - with_retry decorator | | | |
|     | - Exponential backoff + jitter | | | |
|     | - TRANSIENT_ERRORS set (429, 500, 502, 503, 504) | | | |
| 5.2 | **F003: Integrate into claude_code.py** | 1h | 5.1 | M |
|     | - Wrap agent SDK calls | | | |
|     | - Add retry config to .claude-code.json | | | |
| 5.3 | **F003: Write test_retry.py** | 0.5h | 5.1, 3.1 | L |

### Phase 6: AWS Profile Integration (~2h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 6.1 | **F005: Update src/config.py** | 0.5h | None | L |
|     | - Add bedrock_profile to ProjectConfig | | | |
|     | - Parse from .claude-code.json | | | |
| 6.2 | **F005: Create get_boto3_session helper** | 0.5h | 6.1 | L |
|     | - Use profile from config or AWS_PROFILE env | | | |
| 6.3 | **F005: Update bedrock_entrypoint.py** | 0.5h | 6.2 | L |
|     | - Use get_boto3_session for Bedrock client | | | |
| 6.4 | **F005: Update cloudwatch_metrics.py** | 0.5h | 6.2 | L |
|     | - Use get_boto3_session for CloudWatch client | | | |

### Phase 7: Observability - Tracing (~3h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 7.1 | **F008: Create src/tracing.py** | 1.5h | None | L |
|     | - setup_tracing() function | | | |
|     | - TracerProvider + ConsoleSpanExporter | | | |
|     | - Configuration via .claude-code.json | | | |
| 7.2 | **F008: Instrument tool calls** | 1h | 7.1 | M |
|     | - Add spans to security hooks | | | |
|     | - Include tool name, duration, success/failure | | | |
| 7.3 | **F008: Add enable/disable config** | 0.5h | 7.1 | L |
|     | - tracing.enabled in config | | | |
|     | - TRACING_ENABLED env var override | | | |

### Phase 8: Remaining Features (~6h)

| # | Task | Est | Dependencies | Risk |
|---|------|-----|--------------|------|
| 8.1 | **F006: Prompt versioning** | 1h | None | L |
|     | - Add YAML frontmatter to BUILD_PLAN.md | | | |
|     | - Parse version in session_manager.py | | | |
|     | - Include in agent_state.json | | | |
| 8.2 | **F007: Session lock improvements** | 1h | None | L |
|     | - Add jitter to agent-builder.yml | | | |
|     | - Add lock timeout check | | | |
|     | - Add lock status output | | | |
| 8.3 | **F009: Dry run mode** | 1.5h | 1.2 | M |
|     | - Add --dry-run flag | | | |
|     | - Mock SDK client | | | |
|     | - Log what would execute | | | |
| 8.4 | **F010: Issue label filtering** | 1h | None | L |
|     | - Add --labels flag | | | |
|     | - Filter in github_integration.py | | | |
| 8.5 | **F011: Better error messages** | 0.5h | None | L |
|     | - Improve path validation errors | | | |
|     | - Improve bash command errors | | | |
| 8.6 | **F012: Architecture docs** | 0.5h | None | L |
|     | - Add Mermaid diagram to README | | | |
| 8.7 | **F015: Configurable completion signal** | 0.5h | None | L |
|     | - Add to config schema | | | |
|     | - Read in claude_code.py | | | |

**Total Estimated Effort**: ~32 hours

---

## 4. Quality Strategy

**Testing**:
- Unit tests for src/config.py, src/security.py, src/retry.py, src/audit.py
- Target coverage: >60% on core modules
- Edge cases: invalid config, path traversal attempts, transient errors

**Validation**:
- All features verified against acceptance criteria in epcc-features.json
- Pre-commit hooks pass on all code
- mypy --strict passes on all files
- `pytest -v --cov=src` shows >60% coverage

---

## 5. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| mypy strict on legacy code | M | Use overrides for problematic modules, fix incrementally |
| OpenTelemetry adds latency | L | Make tracing disabled by default, enable via config |
| Audit log disk space | M | Implement rotation from day one (10MB × 5 files = 50MB max) |
| Pre-commit slows development | L | Run only on changed files, skip in CI with --no-verify if needed |

**Assumptions**:
- Python 3.11+ is available
- AWS credentials are already configured for Bedrock users
- Existing code patterns should be preserved where possible

**Out of Scope**:
- Major architectural refactoring
- New provider support
- Web UI or dashboard

---

## Implementation Sequence

| Order | Feature | Phase | Est | Dependencies |
|-------|---------|-------|-----|--------------|
| 1 | F016: Version Flag | 1 | 1h | None |
| 2 | F014: Validate Flag | 1 | 2h | None |
| 3 | pyproject.toml | 2 | 1h | None |
| 4 | F013: Pre-commit | 2 | 1.5h | pyproject.toml |
| 5 | F002: Type Safety | 2 | 3.5h | pyproject.toml |
| 6 | F001: Unit Tests | 3 | 5h | pyproject.toml |
| 7 | F004: Audit Trail | 4 | 4h | None |
| 8 | F003: Retry Logic | 5 | 3h | None |
| 9 | F005: AWS Profile | 6 | 2h | None |
| 10 | F008: Tracing | 7 | 3h | None |
| 11 | F006-F012, F015 | 8 | 6h | Various |

---

**Plan Status**: ✅ Ready for implementation with `/epcc-code`
