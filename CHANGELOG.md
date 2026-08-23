# Changelog

## 2026-08-23 — post-PR3 playback resolver candidate
- Current material `main` advanced to `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` after PR #3.
- Four additional `[skip ci]` commits added a playback-time resolver, hourly reliability model, resolver policy configuration and resolver candidate tests.
- Exact delta after PR #3 adds `src/stream_v2/stream_resolver.py`, `src/stream_v2/hourly_health.py`, `config/resolver_policy_v1.json` and `tests/test_stream_v2_candidate.py`.
- These are runtime/config/test changes; no hosted exact-head verification is established for them and `main` remains unprotected with no required status checks.
- PR #1 PASS evidence and Drive EPG V2/V2.1 local evidence do not automatically transfer to this newer resolver candidate.
- Classification remains **STATE REGRESSION IN VERIFICATION / GOVERNANCE EVIDENCE GAP**, now widened by the new stream-resolution candidate.
- STABLE, production/runtime promotion and FORGE registry onboarding remain NOT AUTHORIZED / NOT ESTABLISHED.

## 2026-08-23 — Drive evidence classification correction
- Corrected the prior generic `Drive stale` classification after direct read-back of `ITALIA_TV_HUB_EPG_V2_PROJECT_STATE` and `ITALIA_TV_HUB_EPG_V2_1_PROJECT_STATE`.
- EPG V2 Drive state is aligned with implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34` and correctly records local/off-runner evidence plus zero GitHub workflow runs for that source block.
- EPG V2.1 Drive state is a later local/off-runner candidate with DOCTYPE/GZIP remediation and deterministic local PASS evidence; runtime/promotion is still NOT ESTABLISHED.
- The remaining issue is therefore an exact-source/runtime promotion evidence gap, not generic Drive staleness.
- PR #1 PASS evidence still does not transfer automatically to the post-PR1 implementation commits.
- STABLE and FORGE registry onboarding remain NOT AUTHORIZED / NOT ESTABLISHED.

## 2026-08-23 — governance reconciliation candidate
- PR #1 merge `232ee314146cdf3659ebe7a2e741f06548a5af2c` retained as the last fully evidenced integrated tranche: 280/280 tests PASS, repository test/runtime workflows PASS, 449 streams verified ONLINE, 553 channels published, EPG coverage 8.71%.
- Implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34` was 11 material commits beyond that merge and included EPG V2, final playlist deduplication and regenerated runtime outputs.
- Post-merge implementation commits used `[skip ci]`; exact-source PASS was therefore NOT ESTABLISHED and prior PR #1 PASS evidence was not transferred automatically.
- Added `PROJECT_STATE.md` as the repository-owned durable state record via PR #2; the docs-only merge does not verify runtime.
- STABLE and FORGE registry onboarding are NOT AUTHORIZED / NOT ESTABLISHED by documentary reconciliation.

## 0.2.0
- Core Engine modulare.
- Catalogo sorgenti.
- Downloader HTTP/locale.
- Parser ed exporter M3U.
- Report e test automatici.

## 0.1.0
- Foundation iniziale.
