# ITALIA TV HUB — PROJECT STATE

## Status

Classification: **STATE REGRESSION IN VERIFICATION / GOVERNANCE EVIDENCE GAP**

This file does not infer PASS, STABLE, production authorization, or release authorization from merges or unverified implementation commits.

## Last fully evidenced integrated tranche

PR #1 `fix: harden stream reliability, expand sources, dedupe and add TV guide` was merged on 2026-08-22 as `232ee314146cdf3659ebe7a2e741f06548a5af2c`.

Evidence recorded on that PR:
- `python -m pytest -q`: 280/280 PASS;
- `Test Italia TV Hub`: PASS;
- `Validate Italia TV Hub Runtime`: PASS;
- unique channels before publish policy: 643;
- stream candidates checked: 679;
- verified ONLINE streams: 449;
- runner OFFLINE streams: 230;
- demonstrated hard-fails removed: 90;
- uncertain cases retained: 122;
- final published channels: 553;
- EPG matched: 56;
- EPG unmatched: 536;
- EPG ambiguous: 51;
- EPG coverage: 8.71%.

This evidence applies to the PR #1 candidate/merge tranche only.

## Active implementation source

Current material implementation source head: `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8`.

The previously reconciled implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34` remains the source identity for the aligned Drive EPG V2 evidence, but it is no longer the current repository implementation head.

After the documentary PR #3 merge `b3d770f733f7bea82d01fe25b53578f6fd8aba4a`, four additional material `[skip ci]` commits landed directly on `main`:
- `a6fb0e6978c7b2357eb3b26b747eeb0dfa59a32a` — playback-time resolver candidate;
- `0403812d4014cd5c728a6523a7fe95c42afa623c` — hourly stream reliability model;
- `3eee240706e3f030fe33586e2a7e288c02c15116` — playback resolver policy configuration;
- `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` — resolver candidate test coverage.

The exact delta from PR #3 merge to current `main` adds:
- `src/stream_v2/stream_resolver.py`;
- `src/stream_v2/hourly_health.py`;
- `config/resolver_policy_v1.json`;
- `tests/test_stream_v2_candidate.py`.

These are runtime/config/test changes, not documentary-only changes. They used `[skip ci]`. The repository `main` remains unprotected and has no required status-check enforcement.

Therefore:
- PR #1 PASS evidence does **not** transfer automatically to the current implementation;
- the local/off-runner EPG V2/V2.1 evidence does **not** establish the new playback-resolver runtime behavior;
- adding tests to source is not equivalent to executing those tests on the exact current head.

Current classification for `0f212f5d...`: **EXACT-SOURCE VERIFICATION NOT ESTABLISHED / NEW STREAM-RESOLVER CANDIDATE IN VERIFICATION**.

Repository documentary PR #2 (`81fb5256ee45d739580def51d006efef74062aa6`) and PR #3 (`b3d770f733f7bea82d01fe25b53578f6fd8aba4a`) are documentation/control-plane evidence only; neither verifies the later resolver implementation.

## Drive evidence relationship

The Drive evidence must be interpreted by exact scope:

- `ITALIA_TV_HUB_EPG_V2_PROJECT_STATE` is aligned with implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34`. It explicitly records local/off-runner V2 evidence, zero GitHub workflow runs for that source block, and no production promotion by that V2 block. This remains **ALIGNED LOCAL CANDIDATE EVIDENCE** for that exact source, not evidence for `0f212f5d...`.
- `ITALIA_TV_HUB_EPG_V2_1_PROJECT_STATE` describes a subsequent **OFF-RUNNER V2.1 CANDIDATE** that addresses DOCTYPE/GZIP XMLTV handling and coverage classification. It records local PASS evidence but explicitly states GitHub Actions were not run and the production playlist was not modified by that candidate. Its promotion/runtime evidence remains **NOT ESTABLISHED**.
- No Drive evidence currently establishes the new playback-time resolver/hourly-health candidate added after PR #3.

Accordingly, the cross-source issue remains an **EVIDENCE/PROMOTION GAP**, now widened by a new post-PR3 stream-resolution candidate.

## Authorization boundary

- Current implementation PASS: NOT ESTABLISHED.
- Playback-time resolver/hourly reliability candidate: IN VERIFICATION / exact-source PASS NOT ESTABLISHED.
- Production playlist/runtime acceptance for the post-PR1 implementation deltas: NOT ESTABLISHED.
- EPG V2 runtime/promotion: NOT ESTABLISHED despite aligned local evidence.
- EPG V2.1 runtime/promotion: NOT ESTABLISHED; local/off-runner candidate only.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Next gate

1. Freeze exact implementation candidate `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` unless a newer material source commit deliberately supersedes it.
2. Execute the minimum sufficient deterministic suite on that exact source, including `tests/test_stream_v2_candidate.py`; do not infer PASS from the presence of tests.
3. Run runtime validation for playback resolution, stream publishing and EPG generation on the same exact candidate.
4. Compare resolver behavior and runtime metrics against the PR #1 evidenced baseline and scoped Drive V2/V2.1 evidence.
5. If V2.1 remediation is to be included, bind its exact code/artifact to the repository candidate before promotion.
6. Update Drive only if its scoped evidence changes; preserve correct historical/local-candidate evidence.
7. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into the FORGE product/repository registry; do not invent PRD/REP identifiers automatically.
