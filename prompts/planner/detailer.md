# Planner • Detailer

Expand the given task into the exact template. Focus on **ONE FILE PER TASK**.

**SPECIAL INSTRUCTIONS BY TASK TYPE:**

**For T01 (Project Setup)**: Include bash commands to create the complete folder structure and empty files.

**For File Creation Tasks (T02-T08)**: 
- Focus on creating/editing ONE specific file
- Include the exact file path and content structure
- Provide clear acceptance criteria for that specific file

**For Testing Tasks (T09+)**: 
- Focus on integration testing and validation
- Include specific commands to run and validate

Task: {task_id} — {task_title}

Overall context:
{overall_summary_md}

Return exactly one task block:

# Task {task_id} — {task_title}

## Purpose
(short description about this specific file/component.)

## Inputs
- (Previous task outputs, existing files, requirements)

## Outputs
- (Specific file created/modified with its location)

## Procedure (Intent-level steps)
1. (For T01: Include bash commands like `mkdir -p src/components public && cd src/components && touch App.jsx` )
2. (For file tasks: Create/edit the specific file with proper content)
3. (Include validation steps for this specific file)

## Acceptance Criteria
- (File exists at correct location)
- (File contains required functionality/structure)  
- (File integrates properly with project)

## Dependencies
- (list IDs or “(none)”)

## Risks & Mitigations
- Risk: … → Mitigation: …
