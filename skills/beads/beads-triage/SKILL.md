---
name: beads-triage
description: >-
  Convert a brain-dump, notes file, or scout report into deduplicated Beads (bd)
  epics, tasks, bugs, or features with priorities (-p 0..4) and wired dependencies
  (bd dep add). Use when triaging notes, backlog items, or audit findings into .beads/.
---

# Beads Triage

Turn unstructured notes, brain-dumps, or scout reports into a clean, deduplicated Beads dependency graph.

## Workflow

1. **Inspect existing beads first**:
   ```bash
   bd list --all --json
   ```
   Review open, `in_progress`, and recently closed issues so you never file duplicates.

2. **Deduplicate and group**:
   - If an item matches an existing open bead, update or annotate it (`bd update <id> ...` or `bd comment <id> "..."`) instead of creating a duplicate.
   - Group related items under a parent `epic` (`-t epic`) when 2+ tasks share a deliverable.
   - Assign explicit types (`bug`, `feature`, `task`, `epic`) and priorities:
     - `-p 0`: Critical / outage / security blocker
     - `-p 1`: High / current milestone
     - `-p 2`: Medium / normal work
     - `-p 3`: Low / nice-to-have
     - `-p 4`: Backlog

3. **Create epics and tasks**:
   ```bash
   EPIC=$(bd create "<epic title>" -t epic -p 1 -d "<scope>" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
   T1=$(bd create "<task 1>" -t task -p 1 --parent "$EPIC" -d "<acceptance criteria>" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
   T2=$(bd create "<task 2>" -t bug -p 1 --parent "$EPIC" -d "<repro and fix>" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
   ```

4. **Wire dependencies**:
   - Blocking dependency (`T2` cannot start until `T1` closes):
     ```bash
     bd dep add "$T2" "$T1"
     ```
   - Non-blocking provenance or cross-reference:
     ```bash
     bd dep add "$T2" "$T1" -t discovered-from
     bd dep add "$T2" "$T1" -t related
     ```

5. **Export and report**:
   ```bash
   bd export -o .beads/issues.jsonl
   bd ready
   ```
   Report created/updated IDs, skipped duplicates, wired dependencies, and the resulting `bd ready` queue.
