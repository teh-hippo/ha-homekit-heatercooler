# Release candidates

Use an immutable prerelease for live Home Assistant testing, following the
`ha-govee-led-ble` process. This repository uses HACS source-tag installation,
so stamp the candidate's **committed manifest**, not only a release asset.

1. Prepare a candidate branch containing the reviewed changes on current master.
2. Choose a fresh tag such as `v1.7.0-rc.1.fan-override` and set
   `custom_components/homekit_heatercooler/manifest.json` to `1.7.0rc1`.
   Keep this candidate-only version stamp out of the eventual master merge.
3. Run `bash scripts/check.sh`, commit, and push the candidate branch.
4. Run the **Validate** workflow on that branch and require every check to pass.
5. Tag that exact checked commit and push the tag. The **Prerelease** workflow
   verifies the manifest version, checks both supported core generations, and
   publishes a prerelease with an integration ZIP and SHA-256 checksum.
6. Verify the workflow succeeded, the remote tag points to the checked commit,
   and the downloaded ZIP matches its checksum and tagged integration files.
   Add release notes describing the changes and intended live checks.

## Live testing

Ask for deployment approval before touching the Home Assistant installation.
Capture the installed version and affected entities' restorable state. Discover
the HACS update entity, refresh it with `homeassistant.update_entity`, and use
`update.install` with the **exact RC tag** as its version (enable prereleases
in HACS if needed). Confirm installation, then restart Home Assistant.

Confirm the integration's config entries loaded and its runtime manifest
reports the RC version; HACS download metadata alone is insufficient. Exercise
the feature through normal Home Assistant/HomeKit controls, check logs, and
restore the captured entity state. Install the previous version through HACS
and restart if rollback is needed.

Any follow-up fix gets a new commit, RC number, and tag. Never move or replace a
published RC tag or its assets.
