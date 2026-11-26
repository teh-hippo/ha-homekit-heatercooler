#!/usr/bin/env bash
# Local preflight — mirrors CI checks. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

# Home Assistant arrives through the test plugin in each mutually exclusive
# dependency group. CI runs both; so does this, or the two would not agree.
sync_core() {
    uv sync --locked --no-default-groups --group dev --group "test-$1"
}

assert_core() {
    local expect_version="$1" expect_native="$2" version native
    version="$(uv run --no-sync python -c 'from homeassistant.const import __version__ as v; print(v)')"
    native="$(uv run --no-sync python -c '
import importlib.util

spec = importlib.util.find_spec(
    "homeassistant.components.homekit.type_heater_coolers"
)
print("yes" if spec else "no")
' 2>/dev/null)"
    echo "Home Assistant $version (native HeaterCooler: $native)"
    if [[ "$version" != "$expect_version" ]]; then
        echo "expected Home Assistant $expect_version, got $version" >&2
        exit 1
    fi
    if [[ "$native" != "$expect_native" ]]; then
        echo "expected native HeaterCooler $expect_native, got $native on $version" >&2
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
assert_core 2026.7.4 no
run_tests

echo "=== Test (native core) ==="
sync_core native
assert_core 2026.11.3 yes
run_tests

echo "=== Smoke ==="
uv run --no-sync python -m compileall custom_components

# Leave the working venv on the default group, so a later `uv run` is not a
# surprise.
sync_core legacy

echo ""
echo "✅ All checks passed on both core generations — safe to push."
