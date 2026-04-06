# Foundational Code Quality & CI Pipeline

**Date:** 2026-04-05
**Status:** Draft
**Scope:** Code quality tooling, pre-commit hooks, CI pipeline, coverage tracking

## Motivation

lead-gen-agent has good bones (46 test files, clean migrations, solid project structure) but no automated guardrails. Code can be merged without passing lint, tests, or format checks. Patterns are borrowed from the-hog's mature setup, adapted for our Python + Next.js stack.

## What We're Building

### 1. Ruff Configuration (Python Linting + Formatting)

Add `[tool.ruff]` to `agent/pyproject.toml`:

- **line-length:** 100
- **target-version:** py311
- **Rules enabled:**
  - `E` — pycodestyle errors
  - `F` — pyflakes (unused imports, undefined names)
  - `I` — isort (import sorting)
  - `UP` — pyupgrade (modernize syntax)
  - `B` — bugbear (common pitfalls)
  - `S` — bandit (security: hardcoded passwords, SQL injection, etc.)
- **Formatting:** Ruff formatter (replaces black), configured via `[tool.ruff.format]`
- **Per-file ignores:** `S101` (assert) in test files — tests use assert naturally

Ruff is already in dev dependencies. No new installs needed, just config.

### 2. Pre-commit Hooks (.pre-commit-config.yaml)

New file at repo root:

| Hook | Source | What it does |
|------|--------|-------------|
| `ruff check --fix` | ruff-pre-commit | Auto-fix lint issues on staged Python files |
| `ruff format` | ruff-pre-commit | Auto-format staged Python files |
| `eslint` | local | Lint staged frontend files |
| `detect-secrets` | detect-secrets | Block commits containing API keys/tokens |
| `check-yaml` | pre-commit-hooks | Validate YAML syntax |
| `trailing-whitespace` | pre-commit-hooks | Remove trailing whitespace |
| `end-of-file-fixer` | pre-commit-hooks | Ensure files end with newline |
| `check-added-large-files` | pre-commit-hooks | Block files >500KB (prevent accidental binaries) |

Setup: one-time `pre-commit install` after cloning. Documented in README.

### 3. CI Pipeline (.github/workflows/ci.yml)

**Triggers:** `pull_request` to `main` + `push` to `main`

**Job 1 — python-quality** (ubuntu-latest, Python 3.11):
```
steps:
  - checkout
  - setup-python 3.11
  - pip install -e agent/[dev]
  - ruff check agent/
  - ruff format --check agent/
  - pytest agent/tests/ --cov=agent/src --cov-report=term-missing --tb=short
```

**Job 2 — frontend-quality** (ubuntu-latest, Node 20):
```
steps:
  - checkout
  - setup-node 20
  - npm ci (in frontend/)
  - npm run lint
  - npm run build
```

**Job 3 — ci-gate** (needs: python-quality, frontend-quality):
- Aggregation job for branch protection rule
- Passes only if both upstream jobs pass

**Caching:**
- pip cache: `~/.cache/pip` keyed on `agent/pyproject.toml`
- npm cache: `~/.npm` keyed on `frontend/package-lock.json`

### 4. Test Coverage Tracking

Add `pytest-cov` to dev dependencies in `agent/pyproject.toml`.

Coverage config in `pyproject.toml`:
```toml
[tool.coverage.run]
source = ["agent/src"]
omit = ["agent/tests/*"]

[tool.coverage.report]
show_missing = true
skip_empty = true
```

CI prints coverage to logs on every PR. No minimum threshold enforced — visibility only.

## What We're NOT Doing

- **mypy / type checking** — Ruff catches the highest-value bugs. Mypy can come later.
- **Frontend tests** — No test infrastructure exists yet. Separate initiative.
- **Supabase in CI** — Tests already mock Supabase. No need for a local instance.
- **Coverage enforcement** — Visibility first, thresholds later.
- **Docker build in CI** — Railway handles builds. Not worth the CI minutes yet.
- **Deployment automation** — Out of scope. Current Railway setup works.
- **Security scanning (Dependabot, SAST)** — detect-secrets covers the critical case (leaked keys). Full scanning is a future layer.

## File Changes

| File | Action |
|------|--------|
| `agent/pyproject.toml` | Add `[tool.ruff]`, `[tool.coverage]`, add `pytest-cov` to dev deps |
| `.pre-commit-config.yaml` | New file at repo root |
| `.github/workflows/ci.yml` | New CI workflow |
| `.secrets.baseline` | New file — detect-secrets baseline for existing codebase |

## Implementation Order

1. Ruff config in pyproject.toml (zero-risk, just config)
2. Run `ruff check` and `ruff format` once to fix existing violations
3. Pre-commit config + install
4. CI workflow
5. Verify CI passes on a test PR

## Patterns Borrowed from the-hog

- **Pre-commit as first gate, CI as authoritative gate** — same dual-layer enforcement
- **Lint + typecheck + test as parallel CI jobs** — adapted as ruff + eslint + pytest + next build
- **CI gate job** — aggregation job that branch protection points to
- **Coverage in CI logs** — no external service, just visibility
- **Cache keys on lockfiles** — pip cache keyed on pyproject.toml, npm on package-lock.json
