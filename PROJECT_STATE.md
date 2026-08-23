# ITALIA TV HUB — PROJECT STATE

## Status

Classification: **STATE REGRESSION IN VERIFICATION / GOVERNANCE EVIDENCE GAP**

This file does not infer PASS, STABLE, production authorization, or release authorization from merges, local evidence, or unverified implementation commits.

## Last fully evidenced integrated tranche

PR #1 `fix: harden stream reliability, expand sources, dedupe and add TV guide` was merged on 2026-08-22 as `232ee314146cdf3659ebe7a2e741f06548a5af2c`.

Evidence recorded on that exact tranche:
- `python -m pytest -q`: 280/280 PASS;
- `Test Italia TV Hub`: PASS;
- `Validate Italia TV Hub Runtime`: PASS;
- verified ONLINE streams: 449;
- final published channels: 553;
- EPG matched: 56;
- EPG coverage: 8.71%.

This PASS evidence applies only to the PR #1 candidate/merge tranche.

## Active implementation source

Current material implementation source head: `f903edc9ac35cb9f4202c2c2e7bbba35c03c777a`.

The current head is eight material `[skip ci]` commits beyond the previously reconciled resolver candidate `0f212f5d5ec03eac279cb7d44bbbb36d8ea017f8` and includes all earlier post-PR3 resolver changes plus a new provider-refresh / authoritative-EPG publishing tranche.

The eight new commits add or change:
- provider refresh adapters;
- last-good EPG publication guard;
- authoritative Italian EPG source configuration;
- broad Italian guide backbone settings;
- standalone authoritative EPG builder;
- live multi-source guide fallbacks;
- local authoritative EPG publisher;
- deterministic publisher test coverage.

Exact delta `0f212f5d... -> f903edc9...` changes:
- `config/epg_authoritative_sources.json`;
- `config/settings.json`;
- `scripts/build_epg_authoritative.py`;
- `scripts/epg_refresh_publish.py`;
- `src/epg/last_good_guard.py`;
- `src/stream/provider_adapters.py`;
- `tests/test_epg_refresh_publish.py`.

These are material runtime/config/publishing/test changes. They were committed with `[skip ci]`. GitHub exposes no workflow run associated with exact head `f903edc9...`.

Therefore:
- PR #1 PASS evidence does **not** transfer to the current implementation;
- the earlier `0f212f5d...` resolver candidate has been superseded as the current exact-source boundary before it obtained exact-head execution evidence;
- presence of `tests/test_epg_refresh_publish.py` is not execution evidence;
- no hosted exact-head PASS is established for provider refresh, authoritative EPG generation, last-good publication behavior, or current publishing outputs.

Current classification for `f903edc9...`: **EXACT-SOURCE PASS NOT ESTABLISHED / CURRENT STREAM+EPG PUBLISHER CANDIDATE IN VERIFICATION**.

Repository `main` remains outside a protected required-status evidence path according to the last verified governance read. No PASS or production promotion is inferred from direct commits.

## Historical/scoped Drive evidence relationship

Drive evidence remains authoritative only for its exact stated scope:

- `ITALIA_TV_HUB_EPG_V2_PROJECT_STATE` is aligned local/off-runner candidate evidence for implementation source `1d27af961fb69816a8c17a0062c0ff34aea38b34`. It does not verify the later resolver or publisher candidates.
- `ITALIA_TV_HUB_EPG_V2_1_PROJECT_STATE` is a later local/off-runner candidate for DOCTYPE/GZIP remediation with deterministic local evidence. Runtime/promotion remains NOT ESTABLISHED.
- Neither Drive EPG record establishes exact-source PASS for `f903edc9...`.
- `TIZEN_MEDIA_HUB_V1_PROJECT_STATE` remains separate candidate evidence for the Tizen surface and does not establish Samsung real-device PASS or FORGE onboarding.

No Drive rewrite is required merely because repository implementation advanced; scoped historical evidence must retain its original source identity.

## Authorization boundary

- Current exact implementation PASS: NOT ESTABLISHED.
- Playback resolver/hourly reliability behavior: not independently established on the current exact head.
- Provider refresh adapters: IN VERIFICATION.
- Authoritative EPG builder/publisher: IN VERIFICATION.
- Last-good publication guard: IN VERIFICATION.
- Current EPG/runtime production acceptance: NOT ESTABLISHED.
- STABLE: NOT AUTHORIZED.
- FORGE registry onboarding: NOT ESTABLISHED / OWNER DECISION REQUIRED.

## Repository reconciliation

- PR #2 merged documentary state only.
- PR #3 merged Drive-evidence classification correction only.
- Draft PR #4 is the reversible repository-owned reconciliation for the moving post-PR3 implementation boundary. It must not be interpreted as runtime verification.

## Next gate

1. Freeze exact implementation candidate `f903edc9ac35cb9f4202c2c2e7bbba35c03c777a` unless a newer material source deliberately supersedes it.
2. Execute the minimum sufficient deterministic suite on that exact source, including resolver and authoritative EPG publisher tests.
3. Run same-source runtime validation for stream resolution, provider refresh, EPG generation, last-good publication behavior and published outputs.
4. Compare exact-source stream/EPG metrics against the PR #1 evidenced baseline while preserving the separate historical authority of Drive V2/V2.1.
5. Do not promote STABLE or production state from local or skipped-CI evidence.
6. Decide explicitly whether Italia TV Hub / Tizen Media Hub should be onboarded into the FORGE product/repository registry; do not invent PRD/REP identifiers automatically.
