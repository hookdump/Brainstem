# Brainstem Retrieval Benchmark Report

Generated: 2026-02-25T06:26:31.152010+00:00
Dataset: `benchmarks/retrieval_dataset.json`
Cutoff K: `5`

## Summary

| Backend | Recall@K | nDCG@K | Avg Composed Tokens |
| --- | ---: | ---: | ---: |
| inmemory | 1.000 | 0.882 | 48.9 |
| sqlite | 1.000 | 0.882 | 48.9 |

## Case-level Results (inmemory)

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
