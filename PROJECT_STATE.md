# ITALIA TV HUB — PROJECT STATE

## Status

Classification: **STATE REGRESSION IN VERIFICATION / GOVERNANCE DRIFT**

This file is a documentary reconciliation candidate. It does not infer PASS, STABLE, production authorization, or release authorization from merges or unverified `main` commits.

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

## Current main

Current `main`: `1d27af961fb69816a8c17a0062c0ff34aea38b34`.

`main` is 11 commits ahead of the PR #1 merge and contains material runtime/config/output/test deltas, including:
- final M3U deduplication/post-processing;
- EPG V2 canonical channel identity registry;
- deterministic M3U parser;
- JSON/XMLTV unifier;
- governed EPG source priorities;
- EPG V2 deterministic candidate tests;
- regenerated playlist, health, EPG and publication outputs.

Those post-merge commits were committed with `[skip ci]`. The repository `main` branch is currently not protected and has no required status-check enforcement.

Therefore the PR #1 PASS evidence **does not transfer automatically** to current `main`.

Current classification for the active implementation: **EXACT-CURRENT-MAIN VERIFICATION NOT ESTABLISHED**.

## Drive drift

Drive control-plane documents `ITALIA_TV_HUB_EPG_V2_PROJECT_STATE` and `ITALIA_TV_HUB_EPG_V2_1_PROJECT_STATE` still describe a pre-runtime-validation candidate where GitHub Actions were not run and production playlists were not modified. That is stale relative to PR #1 and also incomplete relative to the 11 post-merge `main` commits.

Drive must not be promoted ahead of a protected/current-source reconciliation.

## Authorization boundary

- Current-main PASS: NOT ESTABLISHED.
- Production playlist/runtime acceptance for the post-PR1 delta: NOT ESTABLISHED.
- EPG V2/V2.1 promotion: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Next gate

1. Freeze an exact current candidate SHA.
2. Run the minimum sufficient deterministic test suite on that exact source.
3. Run runtime validation of stream publishing and EPG generation on the same candidate.
4. Compare current metrics against the PR #1 evidenced baseline.
5. Reconcile `CHANGELOG.md` and the Drive project-state documents only after exact-source evidence is available.
6. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into the FORGE product/repository registry; do not invent PRD/REP identifiers automatically.
