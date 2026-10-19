# V6 compute accounting specification

The user explicitly replaced monetary pricing with token-only reporting.
No currency, estimated invoice, exchange rate or adjustable model price is used.
One input token and one output token each count once in the reported total;
this is an accounting coordinate, not a claim of equal hardware FLOPs.

## Separate quantities

Native metric calls count complete logical task-example evaluations, including
cache hits, Parent traces, local child screening and Full Validation. They exclude
initial/final Optimize diagnostics, final Test, Reflection calls, semantic redraws
and physical transient retries. Native/adapter/admitted batch/external ledger
counts are independently reconciled per cell. Six cells cap native use at18000;
diagnostics add at most1800 logical evaluations and one Test300 per selected final
adds1800. The21600 logical allowance is not a physical request/token ceiling.

The physical append-only ledger records every request reservation, exact identity,
response or failure, cache use and resolution. Per role it reports successes,
failures, input/output tokens, fallback usage and charged accounting. Reliable
provider usage is retained exactly. Missing/unreliable usage uses separately
reported input/output bounds. A failed request has unknown billed usage, not zero:
record its conservative input/output bounds and do not claim an actual invoice.
Conservative bounds and reliable usage remain separate fields.

The unified token ledger is deterministically rebuilt from the hash-checked
physical journal and immutable request/response receipts. It has two views:

1. **Actual dispatch:** first dispatcher receives all observed physical usage.
   Shared hits make no additional paid request. Summing this view exactly matches
   the physical ledger's charged-token total, including conservative amounts.
2. **Standalone attributed:** each arm/repeat/phase receives once the observed
   usage of each unique resolved Solver observation it uses, including semantic
   draws and observed retry bounds. Repeated hits within that arm have zero added
   attributed usage. First use by the other arm receives the same observation
   amount; no new request is made. Fresh Reflection usage stays with its arm.
   This is the cost of replaying each arm with its own exact cache using the
   shared realizations, not a provider invoice. Summing arms may exceed actual
   paid tokens. It removes the artificial second-dispatcher cache advantage.

Every token view reports Solver and Reflection separately. Search cost includes
all search-phase requests, including diagnostics and discarded Reflection draws.
Test is a separate phase. Initial and final diagnostics retain distinct logical
labels and token components. Test token/time metadata is persisted separately
in `test_accounting.json`; the scientific `test_result.json` schema remains
unchanged so completed-result immutability checks stay strict.
Provider retries add tokens/failures but no native logical evaluation.
Scoring/parsing are local CPU work and are not LLM tokens; unresolved work is not
converted into a cheap wrong answer. Wall-clock time per cell is reported
separately and includes its local scoring, IO, backoff and diagnostics.

## Matching and prefix safety

The primary design matches a3000-call Solver cap, allowing at most105 unused
calls from complete-iteration reservation. Actual use can differ. Total tokens
can differ because of Reflection frequency, output lengths, semantic recovery,
provider failures and cache behavior. There is no post-response token hard-cap
claim. No strict total-token/currency budget is promised without a proved
pre-request bound and separately approved policy.

Always label: **Matched solver-evaluation budget, not exactly matched total
compute.** The secondary comparison aligns cumulative standalone-attributed
search tokens. A fixed common-support grid is the ten deciles of the minimum
terminal search-token count across the six cells. It is defined before outcomes;
there is no fitting of weights to favor an arm. Actual-dispatch curves/counters
remain available for operational resource reporting.

Each curve snapshot pins the physical ledger tip. Independent replay recomputes
the token total at that exact prefix; a future response/cache observation cannot
retroactively reduce the discovery cost. A candidate is available only after
its full Validation batch and native archive insertion complete. At an exact
token-coordinate tie, the first observed prefix at that coordinate is used;
later zero-increment events do not backfill an earlier cost point. No interpolation
creates a score before it was measured. No common-support score below the first
complete baseline is fabricated. Prefixes beyond actual support are unavailable.

Offline interrupted-ledger reconstruction reports completed physical usage and
retains unresolved reservations; it does not consume a new execution scope or
automatically resume Solver/search. Same-process retries retain paid outputs.
