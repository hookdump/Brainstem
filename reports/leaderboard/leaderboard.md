# Brainstem Benchmark Leaderboard

Generated: 2026-02-25T07:21:06.812904+00:00
Manifest schema version: 2026-02-25

## Suite: `retrieval_core_v1`

Dataset: `benchmarks/retrieval_dataset.json`
Cutoff K: `5`

| Rank | Backend | Recall@K | nDCG@K | Avg Tokens | Cases |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | inmemory | 1.000 | 0.882 | 48.9 | 10 |
| 2 | sqlite | 1.000 | 0.882 | 48.9 | 10 |

## Contribution Guide

1. Add/modify suite definitions in `benchmarks/suite_manifest.json`.
2. Run `brainstem leaderboard` and commit updated artifacts if needed.
3. Share metric deltas in your PR description for reproducibility.

