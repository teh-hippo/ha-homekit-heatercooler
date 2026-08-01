#!/usr/bin/env bash
# Local preflight — mirrors CI checks. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

# Home Assistant only arrives through pytest-homeassistant-custom-component, so
# the dependency group decides which core generation the suite runs against.
# CI runs both; so does this, or the two would not agree.
sync_core() {
    uv sync --locked --no-default-groups --group dev --group "test-$1"
}

assert_core() {
    local expect="$1" version native
    version="$(uv run --no-sync python -c 'from homeassistant.const import __version__ as v; print(v)')"
    native="$(uv run --no-sync python -c '
import importlib.util

spec = importlib.util.find_spec(
    "homeassistant.components.homekit.type_heater_coolers"
)
print("yes" if spec else "no")
' 2>/dev/null)"
    echo "Home Assistant $version (native HeaterCooler: $native)"
    if [[ "$native" != "$expect" ]]; then
        echo "expected native HeaterCooler $expect, got $native on $version" >&2
        exit 1
    fi
}

run_tests() {
    uv run --no-sync coverage run -m pytest tests/
    uv run --no-sync coverage report \
        --include="custom_components/homekit_heatercooler/*" --fail-under=70
}

echo "=== Lint ==="
sync_core legacy
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .

echo "=== Mypy ==="
uv run --no-sync mypy custom_components/homekit_heatercooler

echo "=== Test (legacy core) ==="
assert_core no
run_tests

echo "=== Test (native core) ==="
sync_core native
assert_core yes
run_tests

echo "=== Smoke ==="
uv run --no-sync python -m compileall custom_components

# Leave the working venv on the default group, so a later `uv run` is not a
# surprise.
sync_core legacy

echo ""
echo "✅ All checks passed on both core generations — safe to push."
