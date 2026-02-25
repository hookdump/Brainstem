# Brainstem Demo Projects

This directory contains runnable demos that show how to use Brainstem as a
shared memory service.

## Available demos

- `rest_context_showcase/`:
  simple REST-based end-to-end flow for storing and retrieving team context.

## Quick start

1. Start Brainstem API:

```bash
brainstem serve-api
```

2. Run the REST demo:

```bash
python demo/rest_context_showcase/run_demo.py
```

