#!/usr/bin/env bash
# Start the full local dev environment (agent + frontend).
# Usage: ./dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$ROOT/agent"
FRONTEND_DIR="$ROOT/frontend"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[dev]${NC} $1"; }
warn()  { echo -e "${YELLOW}[dev]${NC} $1"; }
error() { echo -e "${RED}[dev]${NC} $1"; exit 1; }

# --- Pre-flight checks ---

# Python (need 3.11+)
PYTHON=""
for p in python3.13 python3.12 python3.11 python3; do
  if command -v "$p" &>/dev/null; then
    ver=$("$p" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON="$p"
      break
    fi
  fi
done
[ -z "$PYTHON" ] && error "Python 3.11+ required. Install with: brew install python@3.13"
info "Using $PYTHON ($($PYTHON --version))"

# Node
command -v node &>/dev/null || error "Node.js required. Install with: brew install node"
command -v npm &>/dev/null  || error "npm required."

# --- Agent env check ---
if [ ! -f "$AGENT_DIR/.env" ]; then
  if [ -f "$AGENT_DIR/.env.example" ]; then
    warn "No agent/.env found. Copying from .env.example — fill in your keys."
    cp "$AGENT_DIR/.env.example" "$AGENT_DIR/.env"
  else
    error "No agent/.env file. Create one with ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY."
  fi
fi

# Frontend env check
if [ ! -f "$FRONTEND_DIR/.env.local" ]; then
  if [ -f "$FRONTEND_DIR/.env.local.example" ]; then
    warn "No frontend/.env.local found. Copying from example — fill in your keys."
    cp "$FRONTEND_DIR/.env.local.example" "$FRONTEND_DIR/.env.local"
  else
    error "No frontend/.env.local file."
  fi
fi

# --- Install dependencies ---

# Agent: create venv if needed, install deps
VENV="$AGENT_DIR/.venv"
if [ ! -d "$VENV" ]; then
  info "Creating Python venv..."
  $PYTHON -m venv "$VENV"
fi
info "Installing agent dependencies..."
"$VENV/bin/pip" install -q -r "$AGENT_DIR/requirements.txt"

# Frontend: install node modules if needed
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  info "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
else
  info "Frontend node_modules found, skipping install."
fi

# --- Start services ---

cleanup() {
  info "Shutting down..."
  kill $AGENT_PID $FRONTEND_PID 2>/dev/null || true
  wait $AGENT_PID $FRONTEND_PID 2>/dev/null || true
  info "Done."
}
trap cleanup EXIT INT TERM

# Start agent (port 8000)
info "Starting agent on http://localhost:8000..."
(cd "$AGENT_DIR" && "$VENV/bin/uvicorn" src.main:app --reload --port 8000) &
AGENT_PID=$!

# Start frontend (port 3000)
info "Starting frontend on http://localhost:3000..."
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

echo ""
info "========================================="
info "  Agent:    http://localhost:8000"
info "  Frontend: http://localhost:3000"
info "  Press Ctrl+C to stop both."
info "========================================="
echo ""

wait
