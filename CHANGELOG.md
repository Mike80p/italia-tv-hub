# Changelog

## 2026-08-23 — current stream + authoritative EPG publisher candidate
- Current material implementation source advanced from `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` to `f903edc9ac35cb9f4202c2c2e7bbba35c03c777a` through eight additional material `[skip ci]` commits.
- New delta adds provider refresh adapters, last-good EPG publication guard, authoritative Italian source configuration, broad-guide settings, standalone authoritative EPG builder, live multi-source fallbacks, local authoritative publisher and publisher test coverage.
- Exact changed paths include `config/epg_authoritative_sources.json`, `config/settings.json`, `scripts/build_epg_authoritative.py`, `scripts/epg_refresh_publish.py`, `src/epg/last_good_guard.py`, `src/stream/provider_adapters.py` and `tests/test_epg_refresh_publish.py`.
- GitHub exposes no workflow run for exact head `f903edc9...`; presence of new tests does not establish execution PASS.
- Previous PR #1 PASS evidence and scoped Drive V2/V2.1 local evidence do not transfer to the current stream+EPG publisher candidate.
- Classification remains **STATE REGRESSION IN VERIFICATION / GOVERNANCE EVIDENCE GAP**; exact-source PASS and production/runtime promotion are NOT ESTABLISHED.
- STABLE remains NOT AUTHORIZED; FORGE registry onboarding remains OWNER DECISION REQUIRED.

## 2026-08-23 — post-PR3 playback resolver candidate
- Implementation had advanced to `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` after PR #3 through four `[skip ci]` commits adding playback-time resolver, hourly reliability model, resolver policy and candidate tests.
- That candidate did not establish exact-head execution PASS before being superseded by the later stream+EPG publisher implementation.

## 2026-08-23 — Drive evidence classification correction
- Corrected the prior generic `Drive stale` classification after direct read-back of `ITALIA_TV_HUB_EPG_V2_PROJECT_STATE` and `ITALIA_TV_HUB_EPG_V2_1_PROJECT_STATE`.
- EPG V2 Drive state is aligned with implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34` and correctly records local/off-runner evidence plus zero GitHub workflow runs for that source block.
- EPG V2.1 Drive state is a later local/off-runner candidate with DOCTYPE/GZIP remediation and deterministic local PASS evidence; runtime/promotion is still NOT ESTABLISHED.
- The remaining issue is an exact-source/runtime promotion evidence gap, not generic Drive staleness.

## 2026-08-23 — governance reconciliation candidate
- PR #1 merge `232ee314146cdf3659ebe7a2e741f06548a5af2c` retained as the last fully evidenced integrated tranche: 280/280 tests PASS, repository test/runtime workflows PASS, 449 streams verified ONLINE, 553 channels published, EPG coverage 8.71%.
- Added `PROJECT_STATE.md` as repository-owned durable state via PR #2 and corrected Drive evidence semantics via PR #3; both are documentary only.
- STABLE and FORGE registry onboarding are NOT AUTHORIZED / NOT ESTABLISHED by documentary reconciliation.

## 0.2.0
- Core Engine modulare.
- Catalogo sorgenti.
- Downloader HTTP/locale.
- Parser ed exporter M3U.
- Report e test automatici.

## 0.1.0
- Foundation iniziale.