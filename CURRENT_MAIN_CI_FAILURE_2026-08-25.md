# Italia TV Hub — Current-main hosted CI failure

Date: 2026-08-25
Classification: **STATE REGRESSION / CURRENT-MAIN HOSTED CI FAIL**

## Exact evidence

After documentary PR #6 merged as `a6a81f4e64a3fd46b0293dc58f91888f0e1ce0e6`, the normal `Test Italia TV Hub` push workflow executed on that exact `main` head:

- workflow run: `32802071650` / run #68;
- setup / checkout / Python 3.12 / dependencies: PASS;
- `python -m pytest -q`: **294 PASS / 1 FAIL**;
- failing test: `tests/test_core.py::test_published_report_matches_playlist`;
- observed invariant failure: `output/report.json["channels"] == 781`, while `output/playlist.m3u` contains `688` `#EXTINF` entries;
- workflow conclusion: **FAILURE**.

This reproduces on current `main` the same report↔playlist consistency blocker previously observed by scheduled workflow `Aggiorna Italia TV Hub` run `32799311600` / #185.

## Interpretation boundary

This is stronger evidence than a scheduled-only failure: current `main` now has both scheduled hosted execution FAIL and standard hosted test workflow FAIL on the same published-output consistency invariant.

It does **not** prove that Cloudflare proxy v2.5 (`ff4efd227f85ac7f95a043a06bc9c950e78f6185`) is the direct root cause. The failing assertion concerns repository-published `report.json` and `playlist.m3u` consistency.

Prior PR #1 PASS and exact-source local publisher evidence remain historical/scoped and are not transferred to current `main`.

## Authorization boundary

- trusted scheduled publication: **BLOCKED**;
- current-main hosted CI: **FAIL**;
- Cloudflare deployment: NOT ESTABLISHED / NOT AUTHORIZED;
- production playlist/EPG promotion: NOT ESTABLISHED;
- real-network playback: NOT VERIFIED;
- release / STABLE: NOT AUTHORIZED;
- FORGE onboarding topology: OWNER DECISION REQUIRED.

## Next gate

Identify and correct the minimum responsible report/playlist source-of-truth or generation-order defect, then require a later exact-current-main full hosted GREEN before the failure can be superseded.

No runtime, output, deployment, production or release state is modified by this evidence record.
