# Use Case: PR Handoff and Review Context

Use this when Agent A implements and Agent B reviews in a separate session.

## Step A: Store PR intent and constraints

Remember items to store:

- intended behavior change
- non-goals
- required tests
- migration or compatibility constraints

## Step B: Reviewer recalls context

Query example:

`What were the intended behavior changes, non-goals, and required tests for this PR?`

## Step C: Prompt your coding agent reviewer (copy/paste)

```text
You are reviewing a pull request with strict correctness focus.

Use the Brainstem recall payload to understand intended behavior and limits.
Review for regressions, missing tests, policy violations, and risky assumptions.

Output format:
1) Findings (ordered by severity, with file/line references)
2) Open questions
3) Minimal fix plan

Brainstem recall payload:
<PASTE_JSON_FROM_/v0/memory/recall>
```

