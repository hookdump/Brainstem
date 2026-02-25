# Brainstem Retrieval Benchmark Report

Generated: 2026-02-25T14:26:24.872283+00:00
Dataset: `benchmarks/retrieval_dataset.json`
Cutoff K: `5`

## Summary

| Backend | Graph Mode | Recall@K | nDCG@K | Avg Composed Tokens |
| --- | --- | ---: | ---: | ---: |
| inmemory | off | 1.000 | 0.882 | 48.9 |
| inmemory | on | 1.000 | 0.882 | 38.9 |
| sqlite | off | 1.000 | 0.882 | 48.9 |
| sqlite | on | 1.000 | 0.882 | 38.9 |

## Graph Impact

| Backend | Recall Delta | nDCG Delta | Avg Tokens Delta |
| --- | ---: | ---: | ---: |
| inmemory | +0.000 | +0.000 | -10.0 |
| sqlite | +0.000 | +0.000 | -10.0 |

## Case-level Results (inmemory, graph on)

| Case | Recall | nDCG | Tokens |
| --- | ---: | ---: | ---: |
| deadline_query | 1.000 | 0.631 | 44.0 |
| security_query | 1.000 | 1.000 | 44.0 |
| incident_query | 1.000 | 1.000 | 40.0 |
| release_query | 1.000 | 1.000 | 36.0 |
| cost_query | 1.000 | 0.500 | 44.0 |
| pager_query | 1.000 | 1.000 | 30.0 |
| backup_query | 1.000 | 1.000 | 44.0 |
| sla_query | 1.000 | 1.000 | 38.0 |
| composite_release_security | 1.000 | 0.693 | 36.0 |
| ops_constraints | 1.000 | 1.000 | 33.0 |
