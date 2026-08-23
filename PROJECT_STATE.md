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
Drive `ITALIA_TV_HUB_EPG_LOCAL_PUBLISHER_V1_PROJECT_STATE` explicitly binds local end-to-end evidence to test commit `f903edc9...`.

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

Boundary recorded by the owning Drive evidence:
- Status: **CANDIDATE / LOCAL END-TO-END VERIFIED**;
- GitHub Actions: 0;
- production EPG: not regenerated in that environment;
- automatic two-hour Windows Task Scheduler execution still not installed/verified.

Classification for `f903edc9...`: **STATE ADVANCE IN EXACT-SOURCE LOCAL E2E EVIDENCE ONLY**. Hosted CI and production regeneration remain NOT ESTABLISHED.

### EPG Live Fallback V1 — commit `67d3ac1237d782f30c52500d531f6f05787527e9`
Drive records **CANDIDATE / CONFIG COMMITTED / NO CI**. The config exposes multiple live EPG URLs, but the published playlist still contained the old single EPG URL at evidence time. Client compatibility and production activation remain unverified.

## Current material implementation source

Current `main`: `5aa4a8d1af9a62a8271635581984c0f61692554b`.

The prior Cloudflare proxy candidate `934def9e13aae376e417f717cd648b028f59448c` has been superseded by two additional material `[skip ci]` commits:
- `034deb089f563cae712cdf880841acc03b8a5b45` — `feat(epg): add Cloudflare /epg.xml proxy v2 [skip ci]`;
- `5aa4a8d1af9a62a8271635581984c0f61692554b` — `test(epg): cover Cloudflare proxy v2 [skip ci]`.

Exact compare `934def9e... -> 5aa4a8d1...` changes only:
- `cloudflare/epg-proxy/src/index.js` — 116 changed lines;
- `cloudflare/epg-proxy/tests/proxy.test.js` — 87 changed lines.

The new source therefore materially changes Cloudflare proxy runtime behavior and its tests. The exact head has **no associated GitHub Actions workflow run**. `main` remains unprotected with no required status checks, and the commits themselves use `[skip ci]`.

Therefore:
- the local E2E PASS bound to `f903edc9...` does **not** transfer automatically to `5aa4a8d1...`;
- the presence of proxy-v2 tests is not execution evidence;
- prior unverified `934def9e...` evidence also cannot establish PASS for the new runtime delta;
- no current Drive evidence establishes proxy-v2 exact-source verification;
- hosted exact-head PASS, deployed Worker PASS, production EPG activation and client compatibility remain NOT ESTABLISHED for current `main`.

Current classification for `5aa4a8d1...`: **STATE REGRESSION IN VERIFICATION / CURRENT CLOUDFLARE EPG PROXY V2 CANDIDATE UNVERIFIED** relative to the last exact-source local PASS boundary. This is an evidence/gate regression, not a claim that proxy-v2 behavior is functionally worse.

## Historical/scoped Drive evidence

- EPG V2: aligned local/off-runner evidence for source `1d27af961fb69816a8c17a0062c0ff34aea38b34` only.
- EPG V2.1: local/off-runner candidate; runtime/promotion not established.
- Stream Runtime V1: local candidate evidence; real-network playback not verified.
- EPG Live Fallback V1: config committed/no CI; published playlist activation not established.
- EPG Local Publisher V1: exact-source local E2E evidence for `f903edc9...`; production regeneration not established.
- No Drive record currently establishes `5aa4a8d1...` Cloudflare proxy-v2 verification.

Scoped historical evidence should retain its original source identity rather than be rewritten to imply verification of newer source.

## Authorization boundary

- PR #1 integrated tranche: exact evidence retained.
- `f903edc9...` local publisher: local E2E PASS retained, hosted/production PASS not established.
- Current `5aa4a8d1...` Cloudflare proxy-v2 candidate: exact-source execution PASS NOT ESTABLISHED.
- Cloudflare Worker deployment: NOT ESTABLISHED / NOT AUTHORIZED by this state record.
- Real-network playback: NOT VERIFIED in current stream-runtime evidence.
- Production playlist/EPG promotion: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Repository reconciliation

- PR #2 and PR #3 are documentary-only merged history.
- Draft PR #4 is the reversible repository-owned reconciliation for the moving implementation boundary. It does not verify runtime.

## Next gate

1. Freeze exact candidate `5aa4a8d1af9a62a8271635581984c0f61692554b` unless deliberately superseded.
2. Execute the minimum sufficient exact-source suite, including stream/runtime, publisher and Cloudflare proxy-v2 tests.
3. Verify Cloudflare Worker behavior in an authorized non-production deployment or equivalent deterministic execution before any production claim.
4. Perform one authorized real-network stream validation and verify EPG publication/client compatibility on the same governed source.
5. Preserve `f903edc9...` local E2E evidence as historical exact-source PASS rather than transferring it to newer commits.
6. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into FORGE; do not invent PRD/REP identifiers automatically.
