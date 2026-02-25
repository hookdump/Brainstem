# REST Context Showcase

This demo shows how two agents can write shared memory and then retrieve it
through a single recall query.

## What it demonstrates

- `POST /v0/memory/remember` from one or two agents
- `POST /v0/memory/recall` with budget control
- `GET /v0/memory/{memory_id}` inspect lookup
- optional `POST /v0/memory/reflect` + `GET /v0/jobs/{job_id}` polling

## Prerequisites

- Brainstem API running locally (default: `http://localhost:8080`)

Start API:

```bash
brainstem serve-api
```

## Run

```bash
python demo/rest_context_showcase/run_demo.py
```

Use custom base URL:

```bash
python demo/rest_context_showcase/run_demo.py --base-url http://localhost:8080
```

If API-key auth is enabled, pass the key:

```bash
python demo/rest_context_showcase/run_demo.py --api-key <key>
```

By default, `agent-a` and `agent-b` are the same identity for compatibility
with stricter auth setups. To show true multi-agent behavior (recommended with
auth disabled), set a different second agent:

```bash
python demo/rest_context_showcase/run_demo.py --agent-b a_ops_partner
```

