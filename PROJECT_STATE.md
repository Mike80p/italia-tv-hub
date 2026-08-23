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

Last material implementation source head: `1d27af961fb69816a8c17a0062c0ff34aea38b34`.

That implementation is 11 material commits beyond the PR #1 merge and contains runtime/config/output/test deltas, including:
- final M3U deduplication/post-processing;
- EPG V2 canonical channel identity registry;
- deterministic M3U parser;
- JSON/XMLTV unifier;
- governed EPG source priorities;
- EPG V2 deterministic candidate tests;
- regenerated playlist, health, EPG and publication outputs.

Those implementation commits used `[skip ci]`. The repository branch is not protected and has no required status-check enforcement.

Therefore PR #1 PASS evidence **does not transfer automatically** to the post-PR1 implementation.

Current classification for the active implementation: **EXACT-SOURCE VERIFICATION NOT ESTABLISHED**.

Repository documentary merge PR #2 (`81fb5256ee45d739580def51d006efef74062aa6`) changed only `PROJECT_STATE.md` / `CHANGELOG.md`; it does not alter or verify the implementation baseline.

## Drive evidence relationship

The Drive evidence is not a single stale snapshot and must be interpreted by scope:

- `ITALIA_TV_HUB_EPG_V2_PROJECT_STATE` is aligned with implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34`. It explicitly records local/off-runner V2 evidence, zero GitHub workflow runs for that source block, and no production promotion by that V2 block. This is **ALIGNED LOCAL CANDIDATE EVIDENCE**, not stale evidence.
- `ITALIA_TV_HUB_EPG_V2_1_PROJECT_STATE` describes a subsequent **OFF-RUNNER V2.1 CANDIDATE** that addresses DOCTYPE/GZIP XMLTV handling and coverage classification. It records local PASS evidence but explicitly states GitHub Actions were not run and the production playlist was not modified by that candidate. Its promotion/runtime evidence is therefore **NOT ESTABLISHED**.

Accordingly, the cross-source issue is an **EVIDENCE/PROMOTION GAP**, not generic Drive staleness.

## Authorization boundary

- Post-PR1 implementation PASS: NOT ESTABLISHED.
- Production playlist/runtime acceptance for the post-PR1 implementation delta: NOT ESTABLISHED.
- EPG V2 runtime/promotion: NOT ESTABLISHED despite aligned local evidence.
- EPG V2.1 runtime/promotion: NOT ESTABLISHED; local/off-runner candidate only.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Next gate

1. Freeze the exact implementation candidate SHA to verify (do not use a later documentation-only merge as the runtime source identity).
2. Run the minimum sufficient deterministic suite on that exact implementation source.
3. Run runtime validation of stream publishing and EPG generation on the same candidate.
4. If V2.1 remediation is to be included, first bind its exact code/artifact to the repository candidate and verify it on the same evidence chain.
5. Compare runtime metrics against the PR #1 evidenced baseline and the Drive V2/V2.1 local evidence.
6. Update Drive only if its scoped evidence actually changes; do not rewrite correct historical/local-candidate evidence merely to match a newer Git commit.
7. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into the FORGE product/repository registry; do not invent PRD/REP identifiers automatically.
