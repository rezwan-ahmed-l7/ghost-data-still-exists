# Phase 1 implementation checkpoint

## Scope completed

- code/src/ghost_data_audit/csv_loader.py: strict UTF-8 CSV loading and schema validation for participant-facing CSV files.
- code/src/ghost_data_audit/identity_resolver.py: deterministic current and historical identifier matching bounded by each case's audit_at.
- code/scripts/check_first_five.py: smoke-test runner for the first five public sample requests.
- code/tests/test_identity_resolver.py: unit tests for normalization, current email matching, historical matching, cutoff behavior, and ambiguous matches.

## Deliberately not implemented

The Policy Engine, evidence extraction and replay, Steps Generator, deletion-status decision, and full output.csv generation are outside this checkpoint.

## Run locally

From the repository root:

```bash
python code/scripts/check_first_five.py
PYTHONPATH=code/src python -m unittest discover -s code/tests -v
```

The public sample output status is printed for context only; the smoke test validates identity matching and is not an end-to-end audit evaluation.
