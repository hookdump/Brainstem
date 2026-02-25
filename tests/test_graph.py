from __future__ import annotations

from brainstem.graph import (
    GraphAugmentedRepository,
    InMemoryGraphStore,
    extract_relation_terms,
    parse_relation_weights_json,
)
from brainstem.models import RecallRequest, RememberRequest
from brainstem.store import InMemoryRepository


def test_extract_relation_terms_filters_noise() -> None:
    terms = extract_relation_terms("The migration runbook for kubernetes cluster is ready in 2026.")
    assert "migration" in terms
    assert "kubernetes" in terms
    assert "the" not in terms
    assert "2026" not in terms


def test_inmemory_graph_store_projects_related_edges() -> None:
    store = InMemoryGraphStore()
    store.project_memory("t_graph", "m1", "Kubernetes migration runbook")
    store.project_memory("t_graph", "m2", "Kubernetes rollback runbook")
    related = store.related(
        "t_graph",
        ["m1"],
        exclude_ids={"m1"},
        limit=5,
    )
    assert "m2" in related


def test_graph_augmented_recall_adds_related_memory() -> None:
    repository = InMemoryRepository()
    graph = InMemoryGraphStore()

    remember = repository.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": "t_graph",
                "agent_id": "a_graph",
                "scope": "team",
                "items": [
                    {"type": "fact", "text": "Kubernetes migration runbook"},
                    {"type": "fact", "text": "Kubernetes rollback runbook"},
                ],
            }
        )
    )
    graph.project_memory("t_graph", remember.memory_ids[0], "Kubernetes migration runbook")
    graph.project_memory("t_graph", remember.memory_ids[1], "Kubernetes rollback runbook")

    augmented = GraphAugmentedRepository(repository=repository, graph_store=graph, max_expansion=1)
    recall = augmented.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": "t_graph",
                "agent_id": "a_graph",
                "scope": "team",
                "query": "What kubernetes runbook exists?",
                "budget": {"max_items": 2, "max_tokens": 2000},
            }
        )
    )
    assert len(recall.items) == 2


def test_parse_relation_weights_json() -> None:
    parsed = parse_relation_weights_json('{"reference": 2.5, "keyword": 0.9}')
    assert parsed == {"reference": 2.5, "keyword": 0.9}


def test_graph_augmented_recall_uses_query_seed_candidates() -> None:
    repository = InMemoryRepository()
    graph = InMemoryGraphStore()

    remember = repository.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": "t_graph",
                "agent_id": "a_graph",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Regulation pack RC-22 maps to retention profile RD-91.",
                    },
                    {
                        "type": "policy",
                        "text": "RD-91 enforces 400-day retention and legal hold exports.",
                    },
                    {
                        "type": "fact",
                        "text": "Regulation pack RC-22 summary stays in legal review queue.",
                    },
                ],
            }
        )
    )
    anchor_id, detail_id, noise_id = remember.memory_ids
    graph.project_memory(
        "t_graph",
        anchor_id,
        "Regulation pack RC-22 maps to retention profile RD-91.",
    )
    graph.project_memory(
        "t_graph",
        detail_id,
        "RD-91 enforces 400-day retention and legal hold exports.",
    )
    graph.project_memory(
        "t_graph",
        noise_id,
        "Regulation pack RC-22 summary stays in legal review queue.",
    )

    payload = RecallRequest.model_validate(
        {
            "tenant_id": "t_graph",
            "agent_id": "a_graph",
            "scope": "team",
            "query": "What does regulation pack RC-22 require?",
            "budget": {"max_items": 2, "max_tokens": 2000},
        }
    )
    baseline = repository.recall(payload)
    baseline_ids = [item.memory_id for item in baseline.items]
    assert detail_id not in baseline_ids

    augmented = GraphAugmentedRepository(repository=repository, graph_store=graph, max_expansion=2)
    recall = augmented.recall(payload)
    recall_ids = [item.memory_id for item in recall.items]
    assert detail_id in recall_ids
