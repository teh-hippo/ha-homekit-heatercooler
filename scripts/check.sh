#!/usr/bin/env bash
# Local preflight — mirrors CI checks. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Lint ==="
uv run ruff check .
uv run ruff format --check .

echo "=== Mypy ==="
uv run mypy --ignore-missing-imports custom_components/homekit_heatercooler

echo "=== Smoke ==="
python -m compileall custom_components

echo ""
echo "✅ All checks passed — safe to push."
