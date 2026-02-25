# Use Case: Incident Debugging With Shared Context

Use this when one agent investigates and another agent applies fixes.

## Step A: Store incident evidence

Remember items to store:

- symptom timeline
- affected components
- mitigation steps attempted
- known safe rollback path

## Step B: Recall during debug

Query example:

`What do we know about the outage timeline, blast radius, and safe mitigation path?`

## Step C: Prompt your coding agent (copy/paste)

```text
You are debugging a production incident.

Use the Brainstem recall payload as the incident source of truth.
Do not assume facts not present in the payload.

Tasks:
1) Build a concise incident hypothesis tree.
2) Recommend a lowest-risk mitigation first.
3) List exact code/config checks to run now.
4) Provide a rollback-safe patch plan.

Brainstem recall payload:
<PASTE_JSON_FROM_/v0/memory/recall>
```

