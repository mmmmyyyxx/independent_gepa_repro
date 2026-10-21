# Sole current MATH correctness contract

Current identity: `cevolve_hendrycks_math_v1`. This is a scientific scoring
replacement, based on C-EVOLVE Appendix B.2/J and the explicitly pinned Hendrycks
reference implementation, not a claim of parity with unpublished C-EVOLVE code.

Paper: https://arxiv.org/abs/2509.23331
Reference commit: https://github.com/hendrycks/math/tree/985bdc1696e88e8643f081a0ff4719da39f2ae2a
Vendored source provenance, MIT license and file hashes live in `math_scoring`.

Every MATH correctness path uses `score_math_response(raw_response, gold)`.
Extraction runs original `last_boxed_only_string` then `remove_boxed`. Last boxed
content wins without gold access. Original fbox discovery followed by boxed-only
removal rejects fbox; an unboxed Final Answer or a bare number is not extracted.
Normalization is the pinned finite string transformation; no symbolic algebra,
numeric tolerance, judge, or alternative scorer runs. The original normalization
exception branch compares literal strings. It is not a legacy scorer fallback.
Empty/missing/normalization-invalid gold raises an input error, including when
both prediction and gold are absent. With valid gold extraction failure is zero.
Finish reason remains metadata; it does not add a correctness gate. Raw/reference
resource ceilings are explicit engineering input failures, not incorrect scores.

New cache keys, parsed prediction records and current MATH bindings carry the
contract ID and source digest. Old records and frozen scopes are rejected for
execution rather than reinterpreted. Old manifests and reports remain readable
as historical evidence. Fresh default policies/configs bind the new identity;
existing structural study schemas describe algorithms, not permission to reuse
old checkpoints. New formal execution still requires a fresh source freeze,
manifest, clean-source governance checks and exact API authorization.

Legacy V7, Unified V1, MASPO and mathematical-semantic correctness runtimes are
retired. Source archives contain inventories, plans and tombstones. No historical
grade or saved response is overwritten; any regrade is a separately labeled
offline result. Scores under old contracts are not directly comparable to new
scores. Historical Test continuation scopes cannot execute under this source.

## Aggregation boundary

Existing plurality with tie-abstention is retained. Gold-blind MathVerify
equivalence remains an aggregation-only dependency, separate from correctness.
For example x+x and 2x may share a vote class while only 2x matches gold 2x under
the new scorer. Representative selection can therefore affect final correctness.
This mismatch is disclosed rather than silently changing voting. C-EVOLVE strict
majority/random fallback aggregation is not implemented by this scorer migration.
Non-MATH benchmark rules, prompts, datasets, budgets, scheduling and selection
strategies are unchanged. No model calls or A2 Test execution are part of migration.
