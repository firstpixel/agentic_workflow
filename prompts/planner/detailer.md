# Planner • Detailer

Expand the given task into the exact template. Do **not** invent tools.

**IMPORTANT**: For project setup tasks, include specific folder structure and file creation steps in the Procedure section.

Task: {task_id} — {task_title}

Overall context:
{overall_summary_md}

Return exactly one task block:

# Task {task_id} — {task_title}

## Purpose
(1–2 sentences.)

## Inputs
- …

## Outputs
- …

## Procedure (Intent-level steps)
1. …
2. …

## Acceptance Criteria
- Observable test #1
- Observable test #2

## Dependencies
- (list IDs or “(none)”)

## Risks & Mitigations
- Risk: … → Mitigation: …
