# Archive provenance clarification

The original source.zip preserves the listed working-copy bytes, including uncommitted Unified V1 infrastructure. Two provisional new files, math_scoring/contract.py and math_scoring/score.py, had already been created before that zip was sealed; they are not predecessor-scoring evidence. All original predecessor modules and their per-file hashes remain in the archive. Additional entrypoint and test archives were sealed immediately before their respective retirement. Archives are recovery-only, never imported by the current runtime.
