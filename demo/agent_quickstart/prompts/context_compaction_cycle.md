# Use Case: Long Thread Compaction Cycle

Use this when context is large and expensive to pass into every agent prompt.

## Step A: Compact

Run `/v0/memory/compact` with a targeted query like:

`Summarize final decisions, unresolved blockers, and immediate next actions from this implementation thread.`

Recommended settings:

- `max_source_items`: `16` to `30`
- `target_tokens`: `220` to `700`
- `output_type`: `episode`

## Step B: Recall compacted summary

Run `/v0/memory/recall` with:

`Give me the compacted summary for current implementation decisions and next steps.`

## Step C: Prompt your coding agent (copy/paste)

```text
Use the compacted Brainstem memory payload below as the default working context.
Only ask for a full recall if critical details are missing.

Tasks:
1) Extract decisions, blockers, and next actions.
2) Start with the highest-impact next action.
3) Keep changes aligned with stated constraints.

Compacted memory payload:
<PASTE_JSON_FROM_/v0/memory/recall>
```

