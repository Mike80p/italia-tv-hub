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

Current `main`: `934def9e13aae376e417f717cd648b028f59448c`.

This head is four additional `[skip ci]` commits beyond the locally E2E-verified publisher source `f903edc9...` and adds a Cloudflare live EPG proxy candidate:
- `cloudflare/epg-proxy/src/index.js`;
- `cloudflare/epg-proxy/wrangler.jsonc`;
- `cloudflare/epg-proxy/package.json`;
- `cloudflare/epg-proxy/tests/proxy.test.js`.

Commits add the proxy implementation, Worker config, test package metadata and proxy test coverage. `main` remains unprotected with no required status checks. These commits use `[skip ci]`.

Therefore:
- the local E2E PASS bound to `f903edc9...` does **not** transfer automatically to `934def9e...`;
- presence of Cloudflare proxy tests is not execution evidence;
- no current Drive evidence establishes the Cloudflare proxy candidate;
- hosted exact-head PASS, deployed Worker PASS, production EPG activation and client compatibility are NOT ESTABLISHED for current `main`.

Current classification for `934def9e...`: **STATE REGRESSION IN VERIFICATION / CURRENT CLOUDFLARE EPG PROXY CANDIDATE UNVERIFIED** relative to the prior exact-source local evidence boundary. This is an evidence/gate regression, not a claim that the proxy behavior is functionally worse.

## Historical/scoped Drive evidence

- EPG V2: aligned local/off-runner evidence for source `1d27af961fb69816a8c17a0062c0ff34aea38b34` only.
- EPG V2.1: local/off-runner candidate; runtime/promotion not established.
- Stream Runtime V1: local candidate evidence; real-network playback not verified.
- EPG Live Fallback V1: config committed/no CI; published playlist activation not established.
- EPG Local Publisher V1: exact-source local E2E evidence for `f903edc9...`; production regeneration not established.
- No Drive record currently establishes `934def9e...` Cloudflare proxy verification.

Scoped historical evidence should retain its original source identity rather than be rewritten to imply verification of newer source.

## Authorization boundary

- PR #1 integrated tranche: exact evidence retained.
- `f903edc9...` local publisher: local E2E PASS retained, hosted/production PASS not established.
- Current `934def9e...` Cloudflare proxy candidate: exact-source execution PASS NOT ESTABLISHED.
- Cloudflare Worker deployment: NOT ESTABLISHED / NOT AUTHORIZED by this state record.
- Real-network playback: NOT VERIFIED in current stream-runtime evidence.
- Production playlist/EPG promotion: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Repository reconciliation

- PR #2 and PR #3 are documentary-only merged history.
- Draft PR #4 is the reversible repository-owned reconciliation for the moving implementation boundary. It does not verify runtime.

## Next gate

1. Freeze exact candidate `934def9e13aae376e417f717cd648b028f59448c` unless deliberately superseded.
2. Execute the minimum sufficient exact-source suite, including stream/runtime, publisher and Cloudflare proxy tests.
3. Verify Cloudflare Worker behavior in an authorized non-production deployment or equivalent deterministic execution before any production claim.
4. Perform one authorized real-network stream validation and verify EPG publication/client compatibility on the same governed source.
5. Preserve `f903edc9...` local E2E evidence as historical exact-source PASS rather than transferring it to newer commits.
6. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into FORGE; do not invent PRD/REP identifiers automatically.
