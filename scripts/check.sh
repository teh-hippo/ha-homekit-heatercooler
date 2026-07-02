#!/usr/bin/env bash
# Local preflight — mirrors CI checks. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Lint ==="
uv sync --locked

uv run --no-sync ruff check .
uv run --no-sync ruff format --check .

echo "=== Mypy ==="
uv run --no-sync mypy custom_components/homekit_heatercooler

echo "=== Test ==="
uv run --no-sync coverage run -m pytest tests/
uv run --no-sync coverage report --include="custom_components/homekit_heatercooler/*" --fail-under=70

echo "=== Smoke ==="
uv run --no-sync python -m compileall custom_components

echo ""
echo "✅ All checks passed — safe to push."
