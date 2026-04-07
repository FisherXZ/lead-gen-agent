## Local CI runner — mirrors what GitHub Actions runs
## Usage: make ci          (run everything)
##        make ci-agent    (agent lint + tests only)
##        make ci-frontend (frontend lint + build + tests only)
##        make ci-scrapers (scrapers lint + tests only)

.PHONY: ci ci-agent ci-frontend ci-scrapers

ci: ci-agent ci-scrapers ci-frontend

# ---------------------------------------------------------------------------
# Agent (Python)
# ---------------------------------------------------------------------------

ci-agent:
	@echo "=== Agent: ruff lint ==="
	cd agent && python -m ruff check .
	@echo "=== Agent: ruff format check ==="
	cd agent && python -m ruff format --check .
	@echo "=== Agent: pytest ==="
	cd agent && python -m pytest tests/ -x -q

# ---------------------------------------------------------------------------
# Scrapers (Python)
# ---------------------------------------------------------------------------

ci-scrapers:
	@echo "=== Scrapers: ruff lint ==="
	cd scrapers && python -m ruff check .
	@echo "=== Scrapers: pytest ==="
	cd scrapers && python -m pytest tests/ -x -q

# ---------------------------------------------------------------------------
# Frontend (Node)
# ---------------------------------------------------------------------------

ci-frontend:
	@echo "=== Frontend: install ==="
	cd frontend && npm ci --prefer-offline
	@echo "=== Frontend: ESLint ==="
	cd frontend && npm run lint
	@echo "=== Frontend: build ==="
	cd frontend && npm run build
	@echo "=== Frontend: tests ==="
	cd frontend && npm test -- --watchAll=false --passWithNoTests
