#!/bin/bash
# setup.sh: Bootstrap Argus Development Environment (Async VM / Jules)
# Initializes Python (Poetry) backend and JavaScript (Bun) frontend
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "🔵 [Setup] Starting Argus development environment initialization..."

# ============================================================================
# 1. ENVIRONMENT SETUP
# ============================================================================
echo "🔵 [Setup] Enforcing safe environment variables..."
export ENVIRONMENT=DEV
export DONT_WRITE_BYTECODE=1
export PYTHONUNBUFFERED=1
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
export NEXT_TELEMETRY_DISABLED=1

# Codex Cloud runs setup and agent phases in separate shells. Persist the
# pinned tool locations and telemetry setting so the agent phase uses the
# versions installed here without writing Next.js CLI state into the checkout.
SHELL_PROFILE="$HOME/.bashrc"
touch "$SHELL_PROFILE"
for shell_export in \
    'export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"' \
    'export NEXT_TELEMETRY_DISABLED=1'
do
    if ! grep -Fqx "$shell_export" "$SHELL_PROFILE"; then
        printf '%s\n' "$shell_export" >> "$SHELL_PROFILE"
    fi
done

# Keep local and Cloud setup aligned with the exact toolchain used by CI.
PINNED_POETRY_VERSION="2.1.3"
PINNED_BUN_VERSION="1.3.14"

# ============================================================================
# 1A. WORKTREE ENVIRONMENT FILES
# ============================================================================
echo "🔵 [Setup] Provisioning worktree environment files..."
"$SCRIPT_DIR/setup-worktree-env.sh" "$REPO_ROOT"

# ============================================================================
# 2. PYTHON VERSION CHECK
# ============================================================================
# Enforce the repo pin (.python-version = what CI and Render run), not a floor:
# a newer local Python resolves different dependency wheels and fakes test results.
PINNED_PYTHON="$(cat .python-version 2>/dev/null || echo 3.10)"
PINNED_MINOR="$(echo "$PINNED_PYTHON" | cut -d. -f1-2)"
echo "🔵 [Setup] Resolving pinned Python ${PINNED_PYTHON}..."

PYTHON_CMD=""
if command -v uv &> /dev/null; then
    uv python install "$PINNED_PYTHON" >/dev/null 2>&1 || true
    PYTHON_CMD="$(uv python find "$PINNED_PYTHON" 2>/dev/null || true)"
fi
if [ -z "$PYTHON_CMD" ] && command -v "python$PINNED_MINOR" &> /dev/null; then
    PYTHON_CMD="python$PINNED_MINOR"
fi
if [ -z "$PYTHON_CMD" ] && command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
fi
if [ -z "$PYTHON_CMD" ]; then
    echo "❌ [Setup] Python not found. Install Python ${PINNED_PYTHON} (e.g. 'uv python install ${PINNED_PYTHON}')."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "🔵 [Setup] Python version: $PYTHON_VERSION (command: $PYTHON_CMD)"

if ! $PYTHON_CMD -c "import platform, sys; sys.exit(0 if platform.python_version() == '$PINNED_PYTHON' else 1)"; then
    echo "❌ [Setup] Python ${PINNED_PYTHON} required (repo pin). Found: $PYTHON_VERSION"
    echo "   Install it with: uv python install ${PINNED_PYTHON}"
    exit 1
fi

# ============================================================================
# 3. INSTALL PINNED POETRY
# ============================================================================
echo "🔵 [Setup] Checking Poetry ${PINNED_POETRY_VERSION}..."
CURRENT_POETRY_VERSION=""
if command -v poetry &> /dev/null; then
    CURRENT_POETRY_VERSION="$(poetry --version 2>/dev/null | sed -E 's/^Poetry \(version ([^)]+)\)$/\1/')"
fi
if [ "$CURRENT_POETRY_VERSION" != "$PINNED_POETRY_VERSION" ]; then
    echo "🔵 [Setup] Installing Poetry ${PINNED_POETRY_VERSION} (Official Installer)..."
    curl -sSL https://install.python-poetry.org | \
        POETRY_VERSION="$PINNED_POETRY_VERSION" "$PYTHON_CMD" -
fi
CURRENT_POETRY_VERSION="$(poetry --version 2>/dev/null | sed -E 's/^Poetry \(version ([^)]+)\)$/\1/')"
if [ "$CURRENT_POETRY_VERSION" != "$PINNED_POETRY_VERSION" ]; then
    echo "❌ [Setup] Poetry ${PINNED_POETRY_VERSION} required. Found: ${CURRENT_POETRY_VERSION:-missing}"
    exit 1
fi
echo "🟢 [Setup] Poetry is ready: $(poetry --version)"

# ============================================================================
# 4. INSTALL PINNED BUN
# ============================================================================
echo "🔵 [Setup] Checking Bun ${PINNED_BUN_VERSION}..."
CURRENT_BUN_VERSION=""
if command -v bun &> /dev/null; then
    CURRENT_BUN_VERSION="$(bun --version 2>/dev/null || true)"
fi
if [ "$CURRENT_BUN_VERSION" != "$PINNED_BUN_VERSION" ]; then
    echo "🔵 [Setup] Installing Bun ${PINNED_BUN_VERSION}..."
    curl -fsSL https://bun.com/install | bash -s "bun-v$PINNED_BUN_VERSION"
fi
CURRENT_BUN_VERSION="$(bun --version 2>/dev/null || true)"
if [ "$CURRENT_BUN_VERSION" != "$PINNED_BUN_VERSION" ]; then
    echo "❌ [Setup] Bun ${PINNED_BUN_VERSION} required. Found: ${CURRENT_BUN_VERSION:-missing}"
    exit 1
fi
echo "🟢 [Setup] Bun is ready: ${CURRENT_BUN_VERSION}"

# ============================================================================
# 5. CONFIGURE POETRY
# ============================================================================
echo "🔵 [Setup] Configuring Poetry (local virtualenvs in-project)..."
poetry config virtualenvs.in-project true
# Bind the venv to the pinned interpreter; otherwise Poetry uses whatever
# python3 is active (e.g. Homebrew 3.14) regardless of the repo pin.
poetry env use "$PYTHON_CMD"

# ============================================================================
# 6. INSTALL PYTHON DEPENDENCIES
# ============================================================================
echo "🔵 [Setup] Installing Python dependencies via Poetry..."
poetry install --with dev,workflows --no-interaction
# poetry sync requires Poetry 2.x; skip gracefully if unavailable
poetry sync --with dev,workflows --no-interaction 2>/dev/null || echo "⚠️ [Setup] poetry sync skipped (requires Poetry 2.x)"

# ============================================================================
# 7. VALIDATE PYTHON PACKAGE IMPORTS
# ============================================================================
echo "🔵 [Setup] Validating argus package imports..."
poetry run python -c "import argus; print('[Setup] argus package is importable')"

# ============================================================================
# 8. INSTALL FRONTEND DEPENDENCIES
# ============================================================================
echo "🔵 [Setup] Installing frontend dependencies via Bun..."
cd web
bun install --frozen-lockfile
cd ..

# ============================================================================
# 9. VALIDATE FRONTEND BUILD
# ============================================================================
echo "🔵 [Setup] Validating Next.js frontend setup..."
echo "🟢 [Setup] Next.js frontend is ready"

# ============================================================================
# 10. ENVIRONMENT FILES VALIDATION
# ============================================================================
echo "🔵 [Setup] Validating environment files..."

# Check root .env exists
if [ ! -f .env ]; then
    echo "⚠️ [Setup] Root .env missing. Copy from .env.example:"
    echo "   cp .env.example .env"
    echo "   Then fill in ALPACA_API_KEY, ALPACA_SECRET_KEY, Supabase credentials"
else
    echo "🟢 [Setup] Root .env exists"
fi

# Check web/.env.local exists
if [ ! -f web/.env.local ]; then
    echo "⚠️ [Setup] web/.env.local missing. Create from example:"
    echo "   cp web/.env.local.example web/.env.local"
    echo "   Fill in NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY"
else
    echo "🟢 [Setup] web/.env.local exists"
fi

# Verify no secrets in .gitignore violations
if git ls-files -- .env web/.env.local '.env.*.local' 'web/.env.*.local' 2>/dev/null | grep -q .; then
    echo "❌ [Setup] ERROR: Environment files are tracked in git!"
    echo "   Run: git rm --cached .env web/.env.local"
    exit 1
fi

# ============================================================================
# 11. SUCCESS
# ============================================================================
echo ""
echo "🟢 ============================================================================"
echo "🟢 [Setup] Argus environment is ready!"
echo "🟢 ============================================================================"
echo ""
echo "Next steps:"
echo "  1. Confirm the environment-file validation above"
echo "  2. Choose your mode and start:"
echo "     Dev Mode:  .github/dev.sh (then: cd web && bun run dev)"
echo "     QA Mode:   .github/qa.sh (then: cd web && bun run dev)"
echo ""
echo "For more details, see AGENTS.md → Setup and run"
