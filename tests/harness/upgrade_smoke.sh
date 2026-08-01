#!/usr/bin/env bash
# Drive the two-phase already-paired upgrade smoke.
#
# Pairs a disposable bridge, changes something underneath it, restarts against
# the same config directory, then reconnects with the *persisted* pairing. See
# hap_upgrade_smoke.py for what is asserted and why.
set -euo pipefail

SCENARIO=""
BEFORE_IMAGE=""
AFTER_IMAGE=""
ENGINE="podman"
HARNESS=""
WORKDIR=""
NAME="heatercooler-upgrade"
HA_URL="http://127.0.0.1:18127"
HAP_PORT=21063
KEEP=0

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
    cat <<'EOF'
Usage: upgrade_smoke.sh --scenario SCENARIO --harness DIR [options]

Scenarios:
  core-upgrade  Same integration, core changes underneath a paired bridge.
                The accessory shape must hold.
  adopt         Core serves the entity, then the integration is installed.
                The shape must change and the config number must move with it.

Options:
  --scenario NAME       core-upgrade or adopt (required)
  --harness DIR         Path to a ha-test-harness checkout (required)
  --before-image IMAGE  Image for the first phase
  --after-image IMAGE   Image for the second phase (defaults to --before-image)
  --engine ENGINE       Container engine (default: podman; use podman-sudo
                        locally on a nested userns, docker in CI)
  --workdir DIR         Where the config directory lives (default: mktemp)
  --name NAME           Container name (default: heatercooler-upgrade)
  --keep                Leave the container running afterwards
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scenario) SCENARIO="$2"; shift 2 ;;
        --before-image) BEFORE_IMAGE="$2"; shift 2 ;;
        --after-image) AFTER_IMAGE="$2"; shift 2 ;;
        --engine) ENGINE="$2"; shift 2 ;;
        --harness) HARNESS="$2"; shift 2 ;;
        --workdir) WORKDIR="$2"; shift 2 ;;
        --name) NAME="$2"; shift 2 ;;
        --keep) KEEP=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ -n "$SCENARIO" ]] || { echo "error: --scenario is required" >&2; exit 2; }
[[ -n "$HARNESS" ]] || { echo "error: --harness is required" >&2; exit 2; }
[[ -n "$BEFORE_IMAGE" ]] || { echo "error: --before-image is required" >&2; exit 2; }
AFTER_IMAGE="${AFTER_IMAGE:-$BEFORE_IMAGE}"

case "$SCENARIO" in
    core-upgrade)
        BEFORE_CONFIG="configuration.yaml"
        BEFORE_WITH_INTEGRATION=1
        ;;
    adopt)
        # No integration in the first phase, so core alone decides the
        # accessory type. That is the state an existing user has paired.
        BEFORE_CONFIG="configuration-adopt.yaml"
        BEFORE_WITH_INTEGRATION=0
        ;;
    *) echo "error: unknown scenario $SCENARIO" >&2; exit 2 ;;
esac

WORKDIR="${WORKDIR:-$(mktemp -d)}"
CONFIG="$WORKDIR/config"
SNAPSHOT="$WORKDIR/snapshot.json"
PAIRING="$WORKDIR/pairing.json"

# Home Assistant runs as root inside the container and leaves root-owned files
# in the mounted config directory, so plain rm is not enough to clear a previous
# run. Both the local box and the CI runner have passwordless sudo.
force_rm() {
    [[ -e "$1" ]] || return 0
    rm -rf "$1" 2>/dev/null || sudo rm -rf "$1"
}

# The first phase has to meet an unpaired bridge, so any earlier state must go.
force_rm "$CONFIG"
force_rm "$SNAPSHOT"
force_rm "$PAIRING"
mkdir -p "$CONFIG"

cleanup() {
    if [[ $KEEP -eq 0 ]]; then
        "$ENGINE" rm -f "$NAME" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

PY="$HARNESS/homekit/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "[upgrade] creating the aiohomekit venv"
    (cd "$HARNESS/homekit" && uv venv && uv pip install aiohomekit >/dev/null)
fi

start_ha() {
    local image="$1" with_integration="$2"
    # Stop gracefully so Home Assistant flushes .storage on the way out.
    # ha-bench.sh --recreate force-removes the container, which loses the
    # delayed writes behind the auth tokens and the HomeKit pairing, and a
    # real upgrade is a clean shutdown anyway.
    "$ENGINE" stop --time 60 "$NAME" >/dev/null 2>&1 || true
    # Home Assistant runs as root and leaves root-owned bytecode inside the
    # copied components, which ha-bench.sh cannot clear as the invoking user.
    # Clearing the directory here keeps each phase's component set exact and
    # lets the sudo fallback deal with the ownership.
    force_rm "$CONFIG/custom_components"
    local args=(
        --engine "$ENGINE"
        --name "$NAME"
        --image "$image"
        --config "$CONFIG"
        --host-net
        --recreate
        --component "$HARNESS/mocks/custom_components/mock_climate"
    )
    if [[ "$with_integration" -eq 1 ]]; then
        args+=(--component "$REPO/custom_components/homekit_heatercooler")
    fi
    "$HARNESS/podman/ha-bench.sh" "${args[@]}"
}

wait_for_ha() {
    local i
    for i in $(seq 1 90); do
        if curl -fsS "$HA_URL/api/onboarding" >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done
    curl -fsS "$HA_URL/api/onboarding" >/dev/null
    # The accessory driver only listens once it has built its accessories, so
    # an open HAP port means the database is ready to be read.
    for i in $(seq 1 90); do
        if "$PY" -c "
import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $HAP_PORT)) == 0 else 1)
" 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
    echo "error: HomeKit port $HAP_PORT never opened" >&2
    "$ENGINE" logs --tail 40 "$NAME" >&2 || true
    exit 1
}

state_value() {
    "$ENGINE" exec -i "$NAME" python -c "
import json
from pathlib import Path

state = json.loads(
    next(Path('/config/.storage').glob('homekit.*.state')).read_text()
)
print(state['$1'])
"
}

read_pin() {
    "$PY" - "$CONFIG/home-assistant.log" <<'PY'
from pathlib import Path
import re
import sys

matches = re.findall(
    r"Pincode: (\d{3}-\d{2}-\d{3})",
    Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"),
)
if not matches:
    raise SystemExit("HomeKit pairing code not found")
print(matches[-1])
PY
}

echo "[upgrade] scenario=$SCENARIO workdir=$WORKDIR"

echo "[upgrade] phase 1: $BEFORE_IMAGE"
cp "$REPO/tests/harness/$BEFORE_CONFIG" "$CONFIG/configuration.yaml"
start_ha "$BEFORE_IMAGE" "$BEFORE_WITH_INTEGRATION"
wait_for_ha
HA_TOKEN="$("$PY" "$HARNESS/rest/onboard.py" --url "$HA_URL" --token-only)"
export HA_TOKEN

"$PY" "$REPO/tests/harness/hap_upgrade_smoke.py" \
    --phase before \
    --scenario "$SCENARIO" \
    --snapshot "$SNAPSHOT" \
    --pairing-file "$PAIRING" \
    --config-number "$(state_value config_version)" \
    --harness-homekit "$HARNESS/homekit" \
    --url "$HA_URL" \
    --device-id "$(state_value mac)" \
    --pin "$(read_pin)" \
    --port "$HAP_PORT"

echo "[upgrade] phase 2: $AFTER_IMAGE"
# The second phase always runs the full configuration with the integration
# present. For core-upgrade that is the same file again, so only the image
# moves; for adopt it is the change being tested.
cp "$REPO/tests/harness/configuration.yaml" "$CONFIG/configuration.yaml"
start_ha "$AFTER_IMAGE" 1
wait_for_ha

"$PY" "$REPO/tests/harness/hap_upgrade_smoke.py" \
    --phase after \
    --scenario "$SCENARIO" \
    --snapshot "$SNAPSHOT" \
    --pairing-file "$PAIRING" \
    --config-number "$(state_value config_version)" \
    --harness-homekit "$HARNESS/homekit" \
    --url "$HA_URL" \
    --device-id "$(state_value mac)" \
    --port "$HAP_PORT"
