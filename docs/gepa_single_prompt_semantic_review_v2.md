# GEPA paper/source semantics review, current V4

Reviewed primary sources are the [official ICLR2026 paper](https://proceedings.iclr.cc/paper_files/paper/2026/file/0e9e708b6f48e14fd0ac29e167413f76-Paper-Conference.pdf),
Algorithm1/2 on printed page18 and Observation3/Table3 on pages7-8, and the
[original arXiv v1](https://arxiv.org/pdf/2507.19457v1). Runtime is pinned official
GEPA v0.1.1 at b4dbb55b7601dac448cdb836d5a401ca7d9eb920.
The ICLR PDF SHA256 is d4e29aeb891b8a7f8d99256cb32bc78101e587b5a6c09a6a6ac7e18b8a2a4de4.

The paper tests parent selection while retaining the evolution harness. Local
minibatch improvement precedes full selection-set scoring; final selection uses
aggregate selection-set performance. Pareto selection retains complementary
instance winners and samples after removing dominated candidates.

| Boundary | Current implementation |
|---|---|
| Parent selector | Native current_best versus native pareto: sole arm-dependent optimizer argument |
| Local survival | Same native strict minibatch gate |
| Full selection measurement | Same native full_eval on Validation100 |
| Final output | Same native best_candidate, first maximum on ties |
| Reflection/component/sampler | Same upstream template, per-parent round robin and API RNG wiring |
| Archive | Same native archive, including locally surviving globally inferior candidates |
| Merge | Disabled in both: baseline GEPA; GEPA+Merge is separate |
| Candidate restrictions | V4 removes all reference candidate filters and extra length/nonempty/no-op limits |
| Operational recovery | Same disclosed V3 recovery plus native no-proposal truncation handling |

Strict current_best has one active parent chain, but retains native historical
records. Its parent changes only after strict Validation100 gain. Identical seed
parameters do not imply identical sampled batches under different RNG consumption.

Earlier draft handwritten strict loops and independent sampler RNG were removed
before real execution. Adapter.propose_new_texts=None is explicit to avoid silent
proposal failure. Infrastructure errors escape ordinary native handlers through
typed recovery or genuine integrity aborts. Exhausted bounded reflection generation
uses the native no-proposal path. Candidate content is never assigned guard zeros.

The models,3 text components in one Solver call, frozen MATH memberships,
worked-reference task feedback, resolved-observation pairing and operational
retries/opportunity budgets are shared task adaptations. This compares native
selectors under the user's task harness, not paper benchmark reproduction or
compute matching. Historical Test exposure is disclosed. No native parser or
selection gate is represented as a semantic anti-copy guarantee.

Current release requires V4 offline receipts, frozen committed source and explicit
new user authorization. READY_TO_RUN=false and no real model call is authorized.
