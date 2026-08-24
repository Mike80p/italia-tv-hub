# Changelog

## 2026-08-24 — Cloudflare EPG proxy v2.5 current candidate remains unverified
- Current `main` advanced from the previously reconciled proxy-v2.2 boundary `78c277a3d8d87cbd2e83fa71fe6726793f4f27fb` to `ff4efd227f85ac7f95a043a06bc9c950e78f6185`.
- The material delta is one `[skip ci]` commit: `feat(tv): add Cloudflare proxy v2.5 cleanup`.
- Exact compare adds `scripts/cloudflare_worker_epg_proxy_v2_5.js` with 326 lines of new Cloudflare EPG proxy runtime.
- Exact head `ff4efd22...` has no associated GitHub Actions workflow run; `main` remains unprotected with no required status checks.
- No v2.5-specific Drive evidence record was found.
- Classification: **STATE REGRESSION IN VERIFICATION / CLOUDFLARE EPG PROXY V2.5 CANDIDATE UNVERIFIED / EXACT-SOURCE PASS NOT ESTABLISHED**.
- PR #1 and `f903edc9...` evidence remain historical exact-source boundaries and are not transferred.
- Cloudflare deployment, production EPG activation, real-network playback, STABLE and FORGE onboarding remain NOT ESTABLISHED / NOT AUTHORIZED.

## 2026-08-24 — Cloudflare EPG proxy v2.2 candidate superseded
- `78c277a3d8d87cbd2e83fa71fe6726793f4f27fb` added `cloudflare/epg-proxy-v2.2/index.js` and `cloudflare/epg-proxy-v2.2/test.js` through `[skip ci]` commits.
- No exact-head Actions evidence was established before v2.2 was superseded by v2.5.

## 2026-08-23 — Cloudflare EPG proxy v2 supersedes prior unverified proxy candidate
- Current `main` advanced from `934def9e13aae376e417f717cd648b028f59448c` to `5aa4a8d1af9a62a8271635581984c0f61692554b` through two additional material `[skip ci]` commits.
- `034deb089f563cae712cdf880841acc03b8a5b45` adds Cloudflare `/epg.xml` proxy v2 behavior.
- `5aa4a8d1af9a62a8271635581984c0f61692554b` adds proxy-v2 test coverage.
- Exact compare changes `cloudflare/epg-proxy/src/index.js` and `cloudflare/epg-proxy/tests/proxy.test.js` only, but changes are material runtime+test deltas.
- No GitHub Actions workflow run is associated with exact head `5aa4a8d1...`; the commits use `[skip ci]` and `main` remains without required status checks.
- Classification: **STATE REGRESSION IN VERIFICATION / CLOUDFLARE EPG PROXY V2 CANDIDATE UNVERIFIED**.
- Prior PR #1 and `f903edc9...` exact-source PASS evidence is retained historically and is not transferred.
- Cloudflare deployment, production EPG activation, real-network playback, STABLE and FORGE onboarding remain NOT ESTABLISHED / NOT AUTHORIZED.

## 2026-08-23 — Cloudflare EPG proxy candidate after local publisher verification
- Drive read-back established `f903edc9ac35cb9f4202c2c2e7bbba35c03c777a` as **CANDIDATE / LOCAL END-TO-END VERIFIED** for the EPG local publisher, with XML/GZIP/DOCTYPE/ENTITY/alias/merge/freshness/git/idempotence/UTF-8 checks PASS.
- That Drive evidence explicitly records GitHub Actions = 0 and production EPG not regenerated in that environment; automatic Windows scheduled execution is still not installed/verified.
- Stream Runtime V1 Drive evidence is **LOCALLY VERIFIED** only; GitHub Actions were not run, production playlist was not modified and real-network playback was not verified.
- EPG Live Fallback V1 records config commit `67d3ac1...` with no CI; the published playlist still needed regeneration/patching for the multi-source EPG header to become active.
- After `f903edc9...`, four further `[skip ci]` commits advanced current `main` to `934def9e13aae376e417f717cd648b028f59448c`, adding a Cloudflare live EPG proxy, Worker config, package metadata and proxy tests.
- Exact current Cloudflare proxy PASS is NOT ESTABLISHED; prior `f903edc9...` local E2E PASS does not transfer automatically.
- Classification: **STATE ADVANCE in exact-source local evidence at `f903edc9...`, followed by STATE REGRESSION IN VERIFICATION for `934def9e...`**.
- Cloudflare deployment, production EPG activation, real-network playback, STABLE and FORGE onboarding remain NOT ESTABLISHED / NOT AUTHORIZED.

## 2026-08-23 — current stream + authoritative EPG publisher candidate
- Implementation advanced from `0f212f5d...` to `f903edc9...` through eight material `[skip ci]` commits adding provider refresh adapters, last-good EPG protection, authoritative Italian source configuration, broad-guide settings, standalone builder, multi-source fallbacks, local authoritative publisher and publisher tests.
- Later Drive read-back supplied exact-source local E2E evidence for the publisher at `f903edc9...`; hosted CI and production regeneration remained absent.

## 2026-08-23 — post-PR3 playback resolver candidate
- Implementation had advanced to `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` after PR #3 through four `[skip ci]` commits adding playback-time resolver, hourly reliability model, resolver policy and candidate tests.
- That candidate did not establish exact-head hosted PASS before being superseded.

## 2026-08-23 — Drive evidence classification correction
- EPG V2 Drive state is aligned with implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34` and records local/off-runner evidence only.
- EPG V2.1 remains a local/off-runner candidate with runtime/promotion not established.

## 2026-08-23 — governance reconciliation candidate
- PR #1 merge `232ee314146cdf3659ebe7a2e741f06548a5af2c` remains the last fully evidenced integrated tranche: 280/280 tests PASS, repository test/runtime workflows PASS, 449 streams verified ONLINE, 553 channels published, EPG coverage 8.71%.
- Repository-owned `PROJECT_STATE.md`/`CHANGELOG.md` reconciliation is documentary only and never establishes runtime or release state.

## 0.2.0
- Core Engine modulare.
- Catalogo sorgenti.
- Downloader HTTP/locale.
- Parser ed exporter M3U.
- Report e test automatici.

## 0.1.0
- Foundation iniziale.