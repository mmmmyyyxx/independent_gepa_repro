# V6 post-commit offline acceptance

This review fixes the evidence binding for committed source
`61d42b82b87a4198764641e5b6875a44308b11e5`. It changes no optimizer, scorer,
model, seed, split membership, budget, retry or selection setting. No real model
request, formal authorization or experiment startup is part of this task.

## Exact source and new verification

The complete offline verification was rerun against the committed bytes. Its
[new receipt](offline_gates.json) reports336 passing current tests, including33
dedicated V6 cases, production compileall and the complete fake-provider
lifecycles. Credentials were removed and outgoing sockets were blocked. The
three lifecycle modes each cover both selectors and all three repeats; the
production3000-call boundary also has its own deterministic cases.

The [source binding audit](source_binding.json) independently compares all132
inventory files with their Git blobs at the requested commit. The actual source
inventory and the new verification receipt both identify:

`db31a4113a838bcbe22ef7c429636b20750b140ea7ef1d58a83d0de04789680a`

The earlier complete receipt identifies `c3c8769c5e41...` and cannot authorize
this source. It is preserved as historical evidence. No old receipt hash was
edited or substituted. The previously recorded5346-score replay is
[reused explicitly](scoring_parity_reused.json): its unchanged algorithm and
policy hashes were verified again, rather than claiming another5346 grades
were newly replayed in this task.

The reproducible full verification command is:

```powershell
.venv_math/Scripts/python.exe scripts/verify_single_prompt_gepa_offline.py --bundle data/private_bundles/gepa_single_prompt_math_seed42_repeat3_20261015_v1 --score-replay reports/gepa_single_prompt_v6_preparation_20261019/scoring_parity.json --output runs/gepa_v6_postcommit_61d42b8/offline_gates.json
```

## Real freeze and startup functions, isolated offline

The [handoff audit](handoff_audit.json) uses a separate clean checkout of the
same commit and pinned GEPA. It calls the production `freeze()` and `execute()`
functions with the actual comparison bundle and the newly generated receipt.
Its authorization is a synthetic offline fixture confined to that checkout;
it is revoked after the check. No credentials are copied.

The audit verifies that the old receipt is rejected, an unapproved scope is
rejected, and the new receipt passes the exact source-inventory check during
freeze. It then enters the ordinary production startup branch and validates
source HEAD, inventory, config and authorization hash. A sentinel interrupts
before real client construction, authorization consumption or dispatch.
Wrong source, wrong inventory and changed authorization are independently
rejected. No executable formal scope is created in the working repository.

This is a freeze/startup handoff check, not a full paid experiment. Full
search, audit, selection sealing and Test release are exercised separately by
the newly rerun complete mock lifecycles. The fixture script fingerprint is
recorded in the handoff receipt; its private reproduction artifacts remain
under ignored runs storage.

## Selected Test and resource contract

The user explicitly selected historical Test300 for exploratory comparison.
Its exact file and membership hashes appear in the
[pending authorization request](authorization_request.json). No fresh Test is
certified, created, renamed or resampled. This choice alone does not authorize
API calls. All six searches must close and pass audit before Test opens.

The request retains seed42, repeats1/2/3 per selector, fixed Optimize150 and
Validation100, at most3000 native logical evaluations per cell, and unchanged
Solver/Reflection settings. Six cells allow at most18000 native evaluations,
with diagnostics and final Test accounted separately. Complete-iteration
reservation can leave0-105 native calls unused per cell.

**Matched solver-evaluation budget, not exactly matched total compute.**
Tokens, transient failed attempts and transient retry counts have no hard
ceiling. Diagnostics, Reflection, semantic recovery and physical retries are
not hidden inside the native logical count. Token-only reporting remains
unchanged; no monetary costs are calculated. A later authorization must
explicitly cover these existing resource rules.

## Readiness and publication

Engineering acceptance passes; [READY_TO_RUN remains false](readiness.json).
The authorization request has `execute=false`, no user execution grant and
an exact proposed fresh run path. It cannot pass the formal scope gate. The
[execution plan](execution_plan.json) lists the exact proposed freeze/run commands
for review only; its formal authorization and frozen files do not exist.
Before real calls, use a clean checkout of the exact authorized source, a
new explicit single-use authorization and verified startup identities. Any
change of authorized source requires a new exact scope.

Current report/status changes are local; this acceptance task does not commit,
push or launch a model experiment. The original preparation, publication
checks, historical runs and unrelated capacity-probe artifacts are preserved.
