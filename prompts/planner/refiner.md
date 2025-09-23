# Planner • Refiner

Given a **Refine Request** for a specific task, split it into smaller atomic tasks (≤ 2h), update dependencies, and output updated task blocks. Use exact headings.

{refine_request_md}

### REFINEMENT RESULT (Plan v2)
Replaced: <TaskID>
New: <TaskIDa>, <TaskIDb>

### DEPENDENCIES
<TaskIDa> <- <UpstreamTaskID>
<TaskIDb> <- <TaskIDa>

# Task <TaskIDa> — <Title>
## Purpose
…
## Inputs
- …
## Outputs
- …
## Procedure (Intent-level steps)
1. …
## Acceptance Criteria
- …
## Dependencies
- …
## Risks & Mitigations
- …

# Task <TaskIDb> — <Title>
...
