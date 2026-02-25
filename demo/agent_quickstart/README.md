# Agent Quickstart (10 minutes)

This demo is for people running coding agents and wanting immediate value from
Brainstem without custom architecture work.

It gives you:

- a runnable end-to-end workflow (`remember -> recall -> compact -> recall`)
- concrete copy/paste prompt templates you can feed to your coding agent
- practical use cases for feature work, incident debugging, and PR handoff

## 1) Start Brainstem API

```bash
brainstem serve-api
```

Default URL is `http://localhost:8080`.

## 2) Run the quickstart workflow

```bash
bash demo/agent_quickstart/scripts/run_quickstart.sh
```

With custom values:

```bash
BASE_URL=http://localhost:8080 \
TENANT_ID=t_team \
AGENT_LEAD=a_lead \
AGENT_IMPL=a_impl \
bash demo/agent_quickstart/scripts/run_quickstart.sh
```

If API-key auth is enabled:

```bash
API_KEY=<your-key> bash demo/agent_quickstart/scripts/run_quickstart.sh
```

## 3) Use one of the prompt playbooks

- [feature_continuation.md](./prompts/feature_continuation.md)
- [incident_debugging.md](./prompts/incident_debugging.md)
- [pr_handoff_review.md](./prompts/pr_handoff_review.md)
- [context_compaction_cycle.md](./prompts/context_compaction_cycle.md)

Each file includes:

- what to store in Brainstem
- which recall/compact query to run
- a copy/paste prompt for your coding agent

## Minimal operating pattern

1. Save key facts/policies/decisions with `remember` during work.
2. Start each new coding session with one targeted `recall`.
3. Use `compact` after long threads to create a short reusable summary memory.
4. Paste recall/compact output into the agent prompt template from `prompts/`.

