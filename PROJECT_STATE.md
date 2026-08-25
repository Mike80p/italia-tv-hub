# ITALIA TV HUB — PROJECT STATE

## Status

Classification: **STATE REGRESSION / HOSTED SCHEDULED QUALITY FAIL / GOVERNANCE EVIDENCE GAP**

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

The material commit itself was introduced with `[skip ci]` and had no workflow run bound directly to that SHA. Repository `main` was unprotected with no required status checks at this evidence boundary.

## New hosted scheduled evidence — 2026-08-25

Scheduled workflow `Aggiorna Italia TV Hub` run `32799311600` / run number `185` executed on current documentary `main` head `a6080a7ea29e8f42b8d4b6f0ed69cb1eae9881c8`. That head contains no runtime/config/test delta after material source `ff4efd22...`; the later changes are documentary reconciliation only.

Hosted evidence:
- checkout/setup/dependency installation: PASS;
- `python -m pytest -q`: **294 PASS / 1 FAIL**;
- failing test: `tests/test_core.py::test_published_report_matches_playlist`;
- failure: published `output/report.json` reports `channels = 781`, while current `output/playlist.m3u` contains `688` `#EXTINF` entries;
- generation/publication did not proceed because the test gate failed;
- workflow conclusion: **FAILURE**.

Classification: **STATE REGRESSION / HOSTED SCHEDULED QUALITY FAIL**. This is stronger evidence than the previous “unverified” state for current `main`: current hosted execution is now known to fail a published-output consistency invariant. It does **not** establish that Cloudflare proxy v2.5 itself is the direct root cause, because the failing assertion concerns repository-published report/playlist consistency and the workflow stops before regeneration.

Therefore:
- PR #1 PASS does not transfer to current `main`;
- `f903edc9...` local E2E PASS does not transfer to current `main`;
- proxy v2.2/v2.5 test presence does not establish proxy v2.5 execution PASS;
- current published report/playlist consistency is FAIL in hosted execution;
- deployed Worker PASS, production EPG activation, client compatibility and real-network playback remain NOT ESTABLISHED.

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
- Current `main` hosted scheduled quality gate: **FAIL**.
- Cloudflare Worker deployment: NOT ESTABLISHED / NOT AUTHORIZED by this state record.
- Real-network playback: NOT VERIFIED in current stream-runtime evidence.
- Production playlist/EPG promotion: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Repository reconciliation

- PR #2, PR #3 and PR #4 are documentary-only merged history.
- PR #5 reconciled the material exact-source boundary only and did not verify runtime.
- A documentary-only merge after `ff4efd22...` does not supersede `ff4efd22...` as the material runtime source.
- Scheduled run #185 supplies new hosted evidence for current `main` and supersedes the earlier “hosted execution unknown” boundary with a concrete FAIL for report/playlist consistency.

## Next gate

1. Treat run #185 as authoritative FAIL for current hosted publication quality until superseded by a later exact-current-main GREEN.
2. Determine why `output/report.json` declares 781 channels while `output/playlist.m3u` contains 688 entries; do not regenerate or publish blindly before identifying whether the drift is stale output, generation order, or source-of-truth logic.
3. Correct the minimum responsible runtime/output path and obtain full hosted test GREEN before allowing scheduled publication to resume as a trusted path.
4. Execute the minimum sufficient proxy-v2.5 suite and verify Cloudflare Worker behavior in an authorized non-production deployment or equivalent deterministic execution before any production claim.
5. Perform one authorized real-network stream validation and verify EPG publication/client compatibility on the same governed source.
6. Preserve earlier exact-source evidence boundaries instead of transferring their PASS to newer commits.
7. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into FORGE; do not invent PRD/REP identifiers automatically.
