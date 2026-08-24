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

Material implementation source: `ff4efd227f85ac7f95a043a06bc9c950e78f6185`.

This SHA is the latest commit that materially changes runtime behavior at this reconciliation boundary. Later documentation-only reconciliation commits or merges do **not** create a new runtime candidate and do not invalidate this material-source identity unless runtime/config/test/output behavior changes again.

Since the previously reconciled proxy-v2.2 boundary `78c277a3d8d87cbd2e83fa71fe6726793f4f27fb`, the material implementation advanced by one commit:
- `ff4efd227f85ac7f95a043a06bc9c950e78f6185` — `feat(tv): add Cloudflare proxy v2.5 cleanup [skip ci]`.

Exact compare `78c277a3... -> ff4efd22...` adds:
- `scripts/cloudflare_worker_epg_proxy_v2_5.js` — 326 lines of new Cloudflare EPG proxy runtime.

The exact material source has **no associated GitHub Actions workflow run**. Repository `main` was unprotected with no required status checks at this evidence boundary, and the material commit uses `[skip ci]`.

Therefore:
- PR #1 PASS does not transfer to `ff4efd22...`;
- `f903edc9...` local E2E PASS does not transfer to `ff4efd22...`;
- proxy v2.2 test presence does not establish proxy v2.5 execution evidence;
- EPG Live Fallback V1 remains scoped to its own config commit and does not verify proxy v2.5;
- hosted exact-source PASS, deployed Worker PASS, production EPG activation, client compatibility and real-network playback remain NOT ESTABLISHED.

Current classification for material source `ff4efd22...`: **STATE REGRESSION IN VERIFICATION / CLOUDFLARE EPG PROXY V2.5 CANDIDATE UNVERIFIED / EXACT-SOURCE PASS NOT ESTABLISHED**. This is an evidence/gate regression, not a claim that v2.5 behavior is functionally worse.

## Historical/scoped Drive evidence

- EPG V2: aligned local/off-runner evidence for source `1d27af961fb69816a8c17a0062c0ff34aea38b34` only.
- EPG V2.1: local/off-runner candidate; runtime/promotion not established.
- Stream Runtime V1: local candidate evidence; real-network playback not verified.
- EPG Live Fallback V1: config committed/no CI; published playlist activation not established.
- EPG Local Publisher V1: exact-source local E2E evidence for `f903edc9...`; production regeneration not established.
- No Drive record currently establishes `ff4efd22...` Cloudflare proxy-v2.5 exact-source verification.

Scoped historical evidence retains its source identity and is not rewritten to imply verification of newer source.

## Authorization boundary

- PR #1 integrated tranche: exact evidence retained.
- `f903edc9...` local publisher: local E2E PASS retained; hosted/production PASS not established.
- Material source `ff4efd22...` Cloudflare proxy-v2.5 candidate: exact-source execution PASS NOT ESTABLISHED.
- Cloudflare Worker deployment: NOT ESTABLISHED / NOT AUTHORIZED by this state record.
- Real-network playback: NOT VERIFIED in current stream-runtime evidence.
- Production playlist/EPG promotion: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Repository reconciliation

- PR #2, PR #3 and PR #4 are documentary-only merged history.
- PR #5 reconciles the material exact-source boundary only and does not verify runtime.
- A documentary-only merge after `ff4efd22...` does not supersede `ff4efd22...` as the material runtime source.

## Next gate

1. Freeze exact material candidate `ff4efd227f85ac7f95a043a06bc9c950e78f6185` unless deliberately superseded by another material implementation change.
2. Execute the minimum sufficient exact-source suite for proxy v2.5 plus relevant stream/runtime/publisher regressions.
3. Verify Cloudflare Worker behavior in an authorized non-production deployment or equivalent deterministic execution before any production claim.
4. Perform one authorized real-network stream validation and verify EPG publication/client compatibility on the same governed source.
5. Preserve earlier exact-source evidence boundaries instead of transferring their PASS to newer commits.
6. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into FORGE; do not invent PRD/REP identifiers automatically.
