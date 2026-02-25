# Brainstem Benchmark Leaderboard

Generated: 2026-02-25T14:26:24.063779+00:00
Manifest schema version: 2026-02-25

## Suite: `retrieval_core_v1`

Dataset: `benchmarks/retrieval_dataset.json`
Cutoff K: `5`

| Rank | Backend | Graph | Recall@K | nDCG@K | Avg Tokens | Cases |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | inmemory | off | 1.000 | 0.882 | 48.9 | 10 |
| 2 | inmemory | on | 1.000 | 0.882 | 38.9 | 10 |
| 3 | sqlite | off | 1.000 | 0.882 | 48.9 | 10 |
| 4 | sqlite | on | 1.000 | 0.882 | 38.9 | 10 |

### Graph Quality Dashboard

| Backend | Recall Delta (on-off) | nDCG Delta (on-off) | Avg Tokens Delta |
| --- | ---: | ---: | ---: |
| inmemory | +0.000 | +0.000 | -10.0 |
| sqlite | +0.000 | +0.000 | -10.0 |

## Suite: `relation_graph_v1`

Dataset: `benchmarks/relation_heavy_dataset.json`
Cutoff K: `4`

| Rank | Backend | Graph | Recall@K | nDCG@K | Avg Tokens | Cases |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | inmemory | on | 1.000 | 0.525 | 39.8 | 6 |
| 2 | sqlite | on | 1.000 | 0.525 | 39.8 | 6 |
| 3 | inmemory | off | 0.833 | 0.446 | 51.8 | 6 |
| 4 | sqlite | off | 0.833 | 0.446 | 51.8 | 6 |

### Graph Quality Dashboard

| Backend | Recall Delta (on-off) | nDCG Delta (on-off) | Avg Tokens Delta |
| --- | ---: | ---: | ---: |
| inmemory | +0.167 | +0.079 | -12.0 |
| sqlite | +0.167 | +0.079 | -12.0 |

### Relation Slice Deltas

| Backend | Tag | Recall Delta | nDCG Delta | Avg Tokens Delta |
| --- | --- | ---: | ---: | ---: |
| inmemory | relation | +0.167 | +0.079 | -12.0 |
| inmemory | multi_hop | +0.000 | +0.021 | -11.0 |
| sqlite | relation | +0.167 | +0.079 | -12.0 |
| sqlite | multi_hop | +0.000 | +0.021 | -11.0 |

## Contribution Guide

1. Add/modify suite definitions in `benchmarks/suite_manifest.json`.
2. Run `brainstem leaderboard` and commit updated artifacts if needed.
3. Share metric deltas in your PR description for reproducibility.

