# Brainstem Demo Projects

This directory contains runnable demos that show how to use Brainstem as a
shared memory service.

## Available demos

- `rest_context_showcase/`:
  simple REST-based end-to-end flow for storing and retrieving team context.
- `agent_quickstart/`:
  concrete coding-agent onboarding with copy/paste prompts and a runnable
  remember/recall/compact workflow.

## Quick start

1. Install Brainstem (from repo root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

2. Start Brainstem API:

```bash
brainstem serve-api
```

3. Run the REST demo:

```bash
python demo/rest_context_showcase/run_demo.py
```

4. Run the coding-agent quickstart:

```bash
bash demo/agent_quickstart/scripts/run_quickstart.sh
```
