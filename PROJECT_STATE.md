# ITALIA TV HUB — PROJECT STATE

## Status

Classification: **STATE REGRESSION IN VERIFICATION / GOVERNANCE EVIDENCE GAP**

This file separates exact-source evidence from later implementation deltas and never infers PASS, STABLE, production authorization, or release authorization from merges or `[skip ci]` commits.

## Last fully evidenced integrated tranche

PR #1 merged on 2026-08-22 as `232ee314146cdf3659ebe7a2e741f06548a5af2c`.

Exact-tranche evidence:
- 280/280 tests PASS;
- Test workflow PASS;
- Runtime Validation workflow PASS;
- 449 streams verified ONLINE;
- 553 channels published;
- EPG coverage 8.71%.

Classification: **STATE ADVANCE for the PR #1 tranche only**.

## Later exact-source local evidence

### Stream Runtime V1
Drive `ITALIA_TV_HUB_STREAM_RUNTIME_V1_PROJECT_STATE` records a later candidate as **LOCALLY VERIFIED** with GitHub Actions NOT RUN, production playlist NOT MODIFIED, and real-network playback NOT VERIFIED. Local evidence includes provider adapters/refresh integration, fallback, historical-score tie-break, client payload round-trip and UTF-8 checks.

Classification: **STATE ADVANCE IN LOCAL CANDIDATE EVIDENCE ONLY**. It does not establish hosted CI, real-network playback, production acceptance, or STABLE.

### EPG Local Publisher V1 — exact source `f903edc9ac35cb9f4202c2c2e7bbba35c03c777a`
Drive `ITALIA_TV_HUB_EPG_LOCAL_PUBLISHER_V1_PROJECT_STATE` binds local end-to-end evidence to `f903edc9...`.

Recorded local PASS evidence:
- XML download;
- GZIP;
- safe DOCTYPE sanitization;
- ENTITY blocking;
- playlist alias generation;
- merge;
- freshness gate;
- local git commit;
- second-run idempotence;
- UTF-8 no BOM.

Boundary:
- Status: **CANDIDATE / LOCAL END-TO-END VERIFIED**;
- GitHub Actions: 0;
- production EPG not regenerated in that environment;
- automatic two-hour Windows Task Scheduler execution not installed/verified.

Classification: **STATE ADVANCE IN EXACT-SOURCE LOCAL E2E EVIDENCE ONLY**.

### EPG Live Fallback V1 — commit `67d3ac1237d782f30c52500d531f6f05787527e9`
Drive records **CANDIDATE / CONFIG COMMITTED / NO CI**. Multiple live EPG URLs are configured, but the published playlist still pointed only to the old single EPG URL at evidence time. Client compatibility and production activation remain unverified.

## Current material implementation source

Current `main`: `78c277a3d8d87cbd2e83fa71fe6726793f4f27fb`.

Since the previously reconciled Cloudflare proxy-v2 boundary `5aa4a8d1af9a62a8271635581984c0f61692554b`, `main` advanced by 11 commits. The material current runtime/test delta includes:
- `53c9101cfa931fba061ef0f23a7d594e17cecf72` — `feat(epg): add Cloudflare proxy v2.2 channel mapping [skip ci]`;
- `78c277a3d8d87cbd2e83fa71fe6726793f4f27fb` — `test(epg): cover v2.2 canonical tvg-id mapping [skip ci]`.

Exact compare `5aa4a8d1... -> 78c277a3...` changes:
- `PROJECT_STATE.md` and `CHANGELOG.md` documentary history;
- adds `cloudflare/epg-proxy-v2.2/index.js`;
- adds `cloudflare/epg-proxy-v2.2/test.js`.

The new v2.2 source therefore changes Cloudflare EPG runtime behavior and adds test code. The exact head has **no associated GitHub Actions workflow run**. `main` remains unprotected with no required status checks and the two v2.2 commits use `[skip ci]`.

Therefore:
- PR #1 PASS does not transfer to `78c277a3...`;
- `f903edc9...` local E2E PASS does not transfer to `78c277a3...`;
- test presence is not test execution evidence;
- EPG Live Fallback V1 is scoped evidence for its own config commit and does not verify proxy v2.2;
- hosted exact-head PASS, deployed Worker PASS, production EPG activation, canonical tvg-id client compatibility and real-network playback remain NOT ESTABLISHED.

Current classification for `78c277a3...`: **STATE REGRESSION IN VERIFICATION / CURRENT CLOUDFLARE EPG PROXY V2.2 CANDIDATE UNVERIFIED** relative to the last exact-source evidence boundaries. This is an evidence/gate regression, not a claim that v2.2 behavior is functionally worse.

## Historical/scoped Drive evidence

- EPG V2: aligned local/off-runner evidence for source `1d27af961fb69816a8c17a0062c0ff34aea38b34` only.
- EPG V2.1: local/off-runner candidate; runtime/promotion not established.
- Stream Runtime V1: local candidate evidence; real-network playback not verified.
- EPG Live Fallback V1: config committed/no CI; published playlist activation not established.
- EPG Local Publisher V1: exact-source local E2E evidence for `f903edc9...`; production regeneration not established.
- No Drive record currently establishes `78c277a3...` Cloudflare proxy-v2.2 exact-source verification.

Scoped historical evidence retains its source identity and is not rewritten to imply verification of newer source.

## Authorization boundary

- PR #1 integrated tranche: exact evidence retained.
- `f903edc9...` local publisher: local E2E PASS retained; hosted/production PASS not established.
- Current `78c277a3...` Cloudflare proxy-v2.2 candidate: exact-source execution PASS NOT ESTABLISHED.
- Cloudflare Worker deployment: NOT ESTABLISHED / NOT AUTHORIZED by this state record.
- Real-network playback: NOT VERIFIED in current stream-runtime evidence.
- Production playlist/EPG promotion: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Repository reconciliation

- PR #2, PR #3 and PR #4 are documentary-only merged history.
- This reconciliation is documentary only and does not verify runtime.

## Next gate

1. Freeze exact candidate `78c277a3d8d87cbd2e83fa71fe6726793f4f27fb` unless deliberately superseded.
2. Execute the minimum sufficient exact-source suite, including proxy-v2.2 mapping tests plus relevant stream/runtime/publisher regressions.
3. Verify Cloudflare Worker behavior in an authorized non-production deployment or equivalent deterministic execution before any production claim.
4. Perform one authorized real-network stream validation and verify EPG publication/client compatibility on the same governed source.
5. Preserve earlier exact-source evidence boundaries instead of transferring their PASS to newer commits.
6. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into FORGE; do not invent PRD/REP identifiers automatically.
