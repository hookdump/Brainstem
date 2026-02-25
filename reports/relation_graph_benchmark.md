# Brainstem Retrieval Benchmark Report

Generated: 2026-02-25T14:26:25.724166+00:00
Dataset: `benchmarks/relation_heavy_dataset.json`
Cutoff K: `4`

## Summary

| Backend | Graph Mode | Recall@K | nDCG@K | Avg Composed Tokens |
| --- | --- | ---: | ---: | ---: |
| inmemory | off | 0.833 | 0.446 | 51.8 |
| inmemory | on | 1.000 | 0.525 | 39.8 |
| sqlite | off | 0.833 | 0.446 | 51.8 |
| sqlite | on | 1.000 | 0.525 | 39.8 |

## Graph Impact

| Backend | Recall Delta | nDCG Delta | Avg Tokens Delta |
| --- | ---: | ---: | ---: |
| inmemory | +0.167 | +0.079 | -12.0 |
| sqlite | +0.167 | +0.079 | -12.0 |

## Case-level Results (inmemory, graph on)

| Case | Recall | nDCG | Tokens |
| --- | ---: | ---: | ---: |
| cluster_recovery_steps | 1.000 | 0.631 | 32.0 |
| regulation_requirements | 1.000 | 0.500 | 43.0 |
| overnight_paging_path | 1.000 | 0.631 | 44.0 |
| anomaly_threshold | 1.000 | 0.431 | 40.0 |
| cluster_and_paging | 1.000 | 0.387 | 40.0 |
| compliance_and_billing | 1.000 | 0.571 | 40.0 |

## Relation Slice Metrics (inmemory, graph on)

| Tag | Cases | Recall@K | nDCG@K | Avg Tokens |
| --- | ---: | ---: | ---: | ---: |
| multi_hop | 2 | 1.000 | 0.479 | 40.0 |
| relation | 6 | 1.000 | 0.525 | 39.8 |
| single_hop | 4 | 1.000 | 0.548 | 39.8 |
