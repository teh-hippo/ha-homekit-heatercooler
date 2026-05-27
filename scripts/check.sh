#!/usr/bin/env bash
# Local preflight — mirrors CI checks. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Lint ==="
uv sync --locked

uv run --no-sync ruff check .
uv run --no-sync ruff format --check .

echo "=== Mypy ==="
uv run --no-sync mypy --ignore-missing-imports custom_components/homekit_heatercooler

echo "=== Smoke ==="
uv run --no-sync python -m compileall custom_components

echo ""
echo "✅ All checks passed — safe to push."
