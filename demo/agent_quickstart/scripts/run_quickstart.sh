#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
API_KEY="${API_KEY:-}"
TENANT_ID="${TENANT_ID:-t_agent_quickstart}"
AGENT_LEAD="${AGENT_LEAD:-a_lead}"
AGENT_IMPL="${AGENT_IMPL:-a_impl}"
SCOPE="${SCOPE:-team}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

pretty_print() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  else
    python3 -m json.tool
  fi
}

call_api() {
  local method="$1"
  local path="$2"
  local payload_file="$3"
  local output_file="$4"
  local url="${BASE_URL%/}${path}"

  local header_args=("-H" "content-type: application/json")
  if [[ -n "${API_KEY}" ]]; then
    header_args+=("-H" "x-brainstem-api-key: ${API_KEY}")
  fi

  if [[ -n "${payload_file}" ]]; then
    curl -sS -X "${method}" "${url}" "${header_args[@]}" \
      --data-binary "@${payload_file}" >"${output_file}"
  else
    curl -sS -X "${method}" "${url}" "${header_args[@]}" >"${output_file}"
  fi
}

echo "== Brainstem Agent Quickstart =="
echo "BASE_URL=${BASE_URL}"
echo "TENANT_ID=${TENANT_ID}"
echo "AGENT_LEAD=${AGENT_LEAD}"
echo "AGENT_IMPL=${AGENT_IMPL}"
echo

cat >"${tmp_dir}/remember_lead.json" <<EOF
{
  "tenant_id": "${TENANT_ID}",
  "agent_id": "${AGENT_LEAD}",
  "scope": "${SCOPE}",
  "items": [
    {
      "type": "fact",
      "text": "Feature branch naming format is feat/<issue>-<slug> and must reference a GitHub issue."
    },
    {
      "type": "policy",
      "text": "Every merged PR must pass ruff, mypy, and pytest before merge."
    },
    {
      "type": "event",
      "text": "We are implementing onboarding examples in demo/ for coding agents."
    }
  ]
}
EOF

cat >"${tmp_dir}/remember_impl.json" <<EOF
{
  "tenant_id": "${TENANT_ID}",
  "agent_id": "${AGENT_IMPL}",
  "scope": "${SCOPE}",
  "items": [
    {
      "type": "fact",
      "text": "User requested concrete prompt examples and an easy getting-started flow."
    },
    {
      "type": "event",
      "text": "Implemented strict mypy CI gate and context compaction endpoints in previous milestone."
    }
  ]
}
EOF

echo "-> Remember context (lead)"
call_api "POST" "/v0/memory/remember" "${tmp_dir}/remember_lead.json" "${tmp_dir}/remember_lead.out.json"
cat "${tmp_dir}/remember_lead.out.json" | pretty_print
echo

echo "-> Remember context (impl)"
call_api "POST" "/v0/memory/remember" "${tmp_dir}/remember_impl.json" "${tmp_dir}/remember_impl.out.json"
cat "${tmp_dir}/remember_impl.out.json" | pretty_print
echo

cat >"${tmp_dir}/recall.json" <<EOF
{
  "tenant_id": "${TENANT_ID}",
  "agent_id": "${AGENT_IMPL}",
  "scope": "${SCOPE}",
  "query": "What constraints and recent implementation facts should I follow for this coding task?",
  "budget": { "max_items": 8, "max_tokens": 1800 }
}
EOF

echo "-> Recall context for coding session"
call_api "POST" "/v0/memory/recall" "${tmp_dir}/recall.json" "${tmp_dir}/recall.out.json"
cat "${tmp_dir}/recall.out.json" | pretty_print
echo

cat >"${tmp_dir}/compact.json" <<EOF
{
  "tenant_id": "${TENANT_ID}",
  "agent_id": "${AGENT_IMPL}",
  "scope": "${SCOPE}",
  "query": "Summarize coding workflow constraints and current implementation status.",
  "max_source_items": 16,
  "input_max_tokens": 5000,
  "target_tokens": 260,
  "output_type": "episode"
}
EOF

echo "-> Compact context into reusable summary"
call_api "POST" "/v0/memory/compact" "${tmp_dir}/compact.json" "${tmp_dir}/compact.out.json"
cat "${tmp_dir}/compact.out.json" | pretty_print
echo

cat >"${tmp_dir}/recall_summary.json" <<EOF
{
  "tenant_id": "${TENANT_ID}",
  "agent_id": "${AGENT_IMPL}",
  "scope": "${SCOPE}",
  "query": "Give me the compacted summary for coding workflow constraints.",
  "budget": { "max_items": 6, "max_tokens": 1200 }
}
EOF

echo "-> Recall compacted summary"
call_api "POST" "/v0/memory/recall" "${tmp_dir}/recall_summary.json" "${tmp_dir}/recall_summary.out.json"
cat "${tmp_dir}/recall_summary.out.json" | pretty_print
echo

echo "Quickstart complete."
echo "Next: open demo/agent_quickstart/prompts/ and copy a template into your coding agent."

