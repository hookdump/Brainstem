# Use Case: Feature Continuation Across Sessions

Use this when your coding agent starts a new session and needs prior decisions.

## Step A: Store key decisions

Write decisions as `remember` items during implementation:

- branch and issue conventions
- tests required before merge
- architecture constraints
- current status and blockers

## Step B: Recall before coding

Query example:

`What constraints, decisions, and current status should I follow to continue this feature safely?`

## Step C: Prompt your coding agent (copy/paste)

```text
You are continuing an in-progress feature.

Use the Brainstem recall payload below as authoritative project context.
Prioritize current constraints, active decisions, and unresolved work.

Tasks:
1) Summarize the 5 most important constraints.
2) Propose the next 3 implementation steps.
3) Call out risks that could cause regressions or CI failures.
4) Start implementing step 1 immediately.

Brainstem recall payload:
<PASTE_JSON_FROM_/v0/memory/recall>
```

