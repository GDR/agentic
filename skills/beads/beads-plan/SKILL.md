---
name: beads-plan
description: >-
  Convert an implementation plan, RFC, or design doc into a Beads (bd) epic and
  atomic tasks with --acceptance criteria, wave-based blocking dependencies,
  bidirectional cross-links against existing open beads, and DAG verification
  (bd dep cycles + bd graph --open). Use when turning a structured plan into
  executable Beads tasks.
---

# Beads Plan

Convert a structured implementation plan, RFC, or design doc into a clean, acyclic, parallel-ready Beads execution DAG.

## Workflow

1. **Inspect existing active beads first**:
   ```bash
   bd list --status open,in_progress,blocked --json
   ```
   For large backlogs, supplement with targeted searches (`bd search "<module/symbol>" --status open --json`). Note any existing epics, prerequisites, or overlapping tasks before creating anything.

2. **Decompose the plan into waves and atomic tasks**:
   - Create one parent `epic` (`-t epic`) for the plan (or reuse an existing open epic if the plan extends it).
   - Break work into **atomic, verifiable leaf tasks** (`task`, `feature`, `bug`, `chore`) that a single agent can implement and verify independently.
   - Give every leaf task concrete `--acceptance` criteria (exact command, test, or observable behavior) and `--design` notes when architectural constraints matter.
   - Group tasks into **parallel execution waves** (Wave 0 = no blockers; Wave N depends only on prerequisite tasks in earlier waves — never add artificial serial chains between independent tasks).

3. **Create the epic and tasks**:
   ```bash
   EPIC=$(bd create "<plan title>" -t epic -p 1 -d "<goal and scope>" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

   # Wave 0 (unblocked foundation)
   T1=$(bd create "<foundation task>" -t task -p 1 --parent "$EPIC" \
     -d "<what to build>" --acceptance "<tests/checks that prove done>" \
     --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

   # Wave 1 (blocked by T1 via inline --deps)
   T2=$(bd create "<dependent feature>" -t feature -p 1 --parent "$EPIC" \
     --deps "blocked-by:$T1" -d "<what to build>" --acceptance "<criteria>" \
     --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
   ```
   For large plans (10+ tasks), you may batch edges with `bd dep add --file deps.jsonl` (`{"from":"<blocked>","to":"<blocker>","type":"blocks"}`).

4. **Link tasks (within the plan and against existing beads)**:
   - **Execution order (`blocks`):**
     - Within the plan: `bd dep add <blocked-id> <blocker-id>` (or `bd dep <blocker-id> --blocks <blocked-id>`).
     - **Existing blocks new:** If an existing open/`in_progress` bead must finish first → `bd dep add <new-id> <existing-id>`.
     - **New blocks existing:** If a new task is a prerequisite for an existing open bead → `bd dep add <existing-id> <new-id>`.
   - **Non-blocking semantic links:**
     - Overlapping subsystem/files: `bd dep relate <a-id> <b-id>` (`relates_to`).
     - Verification/test bead for a feature: `bd dep add <test-id> <impl-id> -t validates`.
     - Replaces an obsolete open bead: `bd dep add <new-id> <old-id> -t supersedes`.

5. **Verify the DAG and export**:
   ```bash
   bd dep cycles
   bd graph --open "$EPIC"
   bd export -o .beads/issues.jsonl
   bd ready
   ```
   - `bd dep cycles` must report zero cycles; fix any cycle before finishing.
   - Inspect `bd graph --open "$EPIC"` to confirm Layer 0 (Wave 0) matches the intended immediate starting tasks and parallelizable tasks sit in the same layer.
   - Report the epic ID, task list grouped by wave, cross-links wired to existing beads, and the resulting `bd ready` queue.
