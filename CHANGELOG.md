# CHANGELOG


## v1.2.11 (2026-03-13)

### Build System

- **deps-dev**: Bump ruff in the python-deps group
  ([`7998663`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/799866394e4632efa137bf65023fe33bb92d015d))

### Chores

- **deps**: Weekly lockfile update
  ([`defba57`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/defba57a300dd3c37eab73557f19118eaf7c9dc2))


## v1.2.10 (2026-03-12)

### Build System

- Tighten requires-python to >=3.14.2 for HA 2026.3.1 compatibility
  ([`dae0e23`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/dae0e239b7202bdeb29b8a81fc978a6f380f30ac))

### Chores

- **deps**: Weekly lockfile update
  ([`e021a54`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/e021a54a26ffb39832b8600b83ad079ee75a1689))


## v1.2.9 (2026-03-11)

### Build System

- **deps**: Bump peter-evans/create-pull-request from 7 to 8
  ([`d6637d0`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/d6637d02a7837262901ab58355fccbddb9297539))

### Chores

- **deps**: Weekly lockfile update
  ([`518b44d`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/518b44de77afc4e50732a3925526f2fbde45c515))


## v1.2.8 (2026-03-10)

### Bug Fixes

- Exit 1 on real CI failures, exit 0 on pending checks
  ([`71bbb4d`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/71bbb4d9d590da6131dc245ed832d7008eb5a9c8))


## v1.2.7 (2026-03-10)

### Bug Fixes

- Auto-merge exits cleanly when checks still running
  ([`9d5a7bc`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/9d5a7bc4792ca63ba86f5d40d86f6416fb5a9b95))

### Chores

- **deps**: Weekly lockfile update
  ([`998b640`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/998b6407beb55271f77446955eef21104fa44e40))

### Continuous Integration

- Replace dependabot-automerge with smart auto-merge
  ([`5fb449c`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/5fb449c177b029068ac078ffc7fd4c03c4cb54ea))


## v1.2.6 (2026-03-10)

### Bug Fixes

- Align hacs.json and license format with other HA repos
  ([`67c82ce`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/67c82ce97cdcc5d4301b26145388f9f28749b567))

### Build System

- **deps-dev**: Bump ruff in the python-deps group
  ([`b7c4873`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/b7c4873774b9ed3d6460730defe3e1d6e570fffb))

### Continuous Integration

- Replace Copilot-gated auto-merge with fastify action
  ([`9d58480`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/9d584803447f083d9850f4e6777ff68c832ddd81))


## v1.2.5 (2026-03-05)

### Build System

- **deps**: Bump astral-sh/setup-uv from 6 to 7
  ([`c9433c0`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/c9433c0540b9c4fcdd3295d5e822d463e7d40460))


## v1.2.4 (2026-03-05)

### Build System

- **deps**: Bump actions/checkout from 4 to 6
  ([#4](https://github.com/teh-hippo/ha-homekit-heatercooler/pull/4),
  [`dca217d`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/dca217d6ebbfe47dd72daf03156cce93b1424e0c))

- **deps**: Bump github/codeql-action from 3 to 4
  ([#2](https://github.com/teh-hippo/ha-homekit-heatercooler/pull/2),
  [`e766f1d`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/e766f1d5aaea95a4bfdb2445b7eb7e84b0e9233c))

### Continuous Integration

- Harden dependabot and release flow
  ([`f2d9912`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/f2d991249859e7150945206a483326728abcbc7d))


## v1.2.3 (2026-03-05)

### Bug Fixes

- Scope major-update label creation to repository
  ([`4e89eb3`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/4e89eb318e350561fdffb5d34d0e4219ad4e9394))


## v1.2.2 (2026-03-05)

### Bug Fixes

- Bootstrap major-update label in dependabot workflow
  ([`b093bbf`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/b093bbf169be87a997c724c014ee93561b6f51de))


## v1.2.1 (2026-03-05)

### Bug Fixes

- Correct Copilot reviewer login
  ([`6ab4c97`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/6ab4c97d30d040badac8fc9cb9284e733ffc1512))


## v1.2.0 (2026-03-05)

### Features

- Add HomeKit brand overlay and Python 3.14 support
  ([`218cfb9`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/218cfb9efd1c11e0fbe8808dfcd947ba4655b7b2))


## v1.1.9 (2026-03-01)

### Bug Fixes

- Run patch status callbacks on event loop
  ([`7852a16`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/7852a16900ea491104c3fd88f9734c1804e7f779))


## v1.1.8 (2026-03-01)

### Bug Fixes

- Use thread-safe dispatcher signal
  ([`ccfc3e5`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/ccfc3e576f57973175c10da0250e8a42432b94c6))

### Chores

- **lock**: Sync project version in uv.lock
  ([`73e6cd8`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/73e6cd88300d1ccdb5ebc9c4ab70b3b4ac890fc0))

### Continuous Integration

- Publish latest release alias
  ([`95b96f3`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/95b96f3fa32ef04f5ce8147236eead003679aad1))


## v1.1.7 (2026-02-26)

### Bug Fixes

- **release**: Handle missing latest tag ref
  ([`dce7d3c`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/dce7d3c990843a0f9b1bff10854df81453bcb4c5))


## v1.1.6 (2026-02-26)

### Bug Fixes

- Refresh heatercooler diagnostics status
  ([`a448d88`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/a448d8878f8ffbedfeb0f0f1664b0572e72af4b2))

### Chores

- **lock**: Sync project version in uv.lock
  ([`a436cf4`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/a436cf43b9b5771e41c3a8787bbc116a639d449e))

### Continuous Integration

- **release**: Maintain latest tag
  ([`f1f536d`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/f1f536ddb7585db92bc72407ca1706c18952c8c9))


## v1.1.5 (2026-02-21)

### Bug Fixes

- Instantiate options flow without args
  ([`a7dd525`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/a7dd5251b575d19fba801d8c6f7c5fbdfc12c81a))


## v1.1.4 (2026-02-21)

### Bug Fixes

- Make diagnostics update thread-safe
  ([`e20afae`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/e20afae1acf6e037b6d9429c754604841d02e4bd))


## v1.1.3 (2026-02-21)

### Bug Fixes

- Resolve options flow 500 error
  ([`5167c1c`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/5167c1cbf3fe829203b83e70d49451b440840d83))


## v1.1.2 (2026-02-21)

### Bug Fixes

- Add patch diagnostics sensor
  ([`517ac6d`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/517ac6dfa26e59507e79b65a51d29d06bbf1674c))


## v1.1.1 (2026-02-21)

### Bug Fixes

- Classify integration as service
  ([`3b83217`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/3b8321727ac621a8e547a0f38597ce8b8805f201))

### Documentation

- Clarify why this exists
  ([`39cdb3a`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/39cdb3ac291093216b40449f0571e40ca22ed2d2))

- Refine README wording
  ([`4d8faec`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/4d8faec69f0860a097f488bccef32dfcef0ef76f))


## v1.1.0 (2026-02-21)

### Bug Fixes

- Sort manifest keys for hassfest
  ([`6b3b8ce`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/6b3b8ce1379960bc065933cfc548b1dca787c9f2))

### Features

- Add UI configuration flow
  ([`7df7b6a`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/7df7b6a57970db3772721cff0f77a8facc23d4ff))


## v1.0.0 (2026-02-21)


## v0.1.2 (2026-02-21)

### Bug Fixes

- Sort manifest keys for hassfest
  ([`f37da49`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/f37da4926f34d8e91ccf361269e30792f03d853b))

### Continuous Integration

- Align quality and release automation
  ([`9fde4a8`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/9fde4a84abb302f2d93448a65ad187a68e435f68))

### Documentation

- Explain patch lifecycle and upgrade caveats
  ([`6ef4dae`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/6ef4daeb84349ba03a7ab242e6ec08f459e6c6f5))


## v0.1.1 (2026-02-13)

### Bug Fixes

- Use entityfilter constants for include/exclude entities
  ([`268e1a3`](https://github.com/teh-hippo/ha-homekit-heatercooler/commit/268e1a36847e831677e6b8a5f1eaf48e00132aed))


## v0.1.0 (2026-02-13)

- Initial Release
