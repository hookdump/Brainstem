# Brainstem Retrieval Benchmark Report

Generated: 2026-02-25T07:33:27.197406+00:00
Dataset: `benchmarks/retrieval_dataset.json`
Cutoff K: `5`

## Summary

| Backend | Graph Mode | Recall@K | nDCG@K | Avg Composed Tokens |
| --- | --- | ---: | ---: | ---: |
| inmemory | off | 1.000 | 0.882 | 48.9 |
| inmemory | on | 1.000 | 0.882 | 48.9 |
| sqlite | off | 1.000 | 0.870 | 50.0 |
| sqlite | on | 0.900 | 0.502 | 50.1 |

## Graph Impact

| Backend | Recall Delta | nDCG Delta | Avg Tokens Delta |
| --- | ---: | ---: | ---: |
| inmemory | +0.000 | +0.000 | +0.0 |
| sqlite | -0.100 | -0.368 | +0.1 |

## Case-level Results (inmemory, graph on)

| Case | Recall | nDCG | Tokens |
| --- | ---: | ---: | ---: |
| deadline_query | 1.000 | 0.631 | 47.0 |
| security_query | 1.000 | 1.000 | 47.0 |
| incident_query | 1.000 | 1.000 | 50.0 |
| release_query | 1.000 | 1.000 | 47.0 |
| cost_query | 1.000 | 0.500 | 53.0 |
| pager_query | 1.000 | 1.000 | 48.0 |
| backup_query | 1.000 | 1.000 | 47.0 |
| sla_query | 1.000 | 1.000 | 48.0 |
| composite_release_security | 1.000 | 0.693 | 50.0 |
| ops_constraints | 1.000 | 1.000 | 52.0 |
