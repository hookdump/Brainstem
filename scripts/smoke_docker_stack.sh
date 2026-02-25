#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"

echo "Checking health..."
curl -fsS "${BASE_URL}/healthz" >/tmp/brainstem_health.json
cat /tmp/brainstem_health.json
echo

echo "Writing memory item..."
curl -fsS -X POST "${BASE_URL}/v0/memory/remember" \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "t_smoke",
    "agent_id": "a_smoke",
    "scope": "team",
    "items": [
      {"type": "fact", "text": "Docker smoke test memory item.", "trust_level": "trusted_tool"}
    ]
  }' >/tmp/brainstem_remember.json
cat /tmp/brainstem_remember.json
echo

echo "Running recall..."
curl -fsS -X POST "${BASE_URL}/v0/memory/recall" \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "t_smoke",
    "agent_id": "a_smoke",
    "scope": "team",
    "query": "What docker smoke memory exists?"
  }' >/tmp/brainstem_recall.json
cat /tmp/brainstem_recall.json
echo

echo "Smoke test completed."
