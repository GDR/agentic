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

3. **Create epics and tasks (in `backlog` with readable slug IDs)**:
   - Always pass `-s backlog` (hidden from `bd ready` until user-vetted/promoted to `open`), unless the user explicitly asks to triage directly into `open`.
   - Always pass an explicit readable `--id` — never rely on auto-generated 3-char hashes or numeric suffixes:
     - Epic: `--id <prefix>-<topic>` (1–2 lowercase kebab words).
     - Child tasks: `--id <epic-id>.<short-slug>` (2–3 lowercase kebab words, total ID <= 35 chars) attached via `--deps "parent-child:<epic-id>"` (`bd create` rejects `--id` combined with `--parent`).
     - Standalone tasks: `--id <prefix>-<subsystem>-<short-slug>`.
   ```bash
   EPIC="<prefix>-<topic>"
   bd create "<epic title>" --id "$EPIC" -t epic -p 1 -s backlog -d "<scope>"

   T1="${EPIC}.<short-slug>"
   bd create "<task 1>" --id "$T1" -t task -p 1 -s backlog \
     --deps "parent-child:$EPIC" -d "<acceptance criteria>"

   T2="${EPIC}.<short-slug-2>"
   bd create "<task 2>" --id "$T2" -t bug -p 1 -s backlog \
     --deps "parent-child:$EPIC" -d "<repro and fix>"
   ```

4. **Wire dependencies (including existing beads)**:
   - Blocking dependency (`T2` cannot start until `T1` closes):
     ```bash
     bd dep add "$T2" "$T1"
     ```
   - **Cross-link against existing active beads** (both directions):
     - Existing open/`in_progress` bead blocks new bead: `bd dep add <new-id> <existing-id>`
     - New bead blocks existing open bead: `bd dep add <existing-id> <new-id>`
     - Overlapping subsystem/files: `bd dep relate <new-id> <existing-id>`
   - Non-blocking provenance or validation:
     ```bash
     bd dep add "$T2" "$T1" -t discovered-from
     bd dep add "$T2" "$T1" -t validates
     ```

5. **Verify, export, and report**:
   ```bash
   bd dep cycles
   bd export -o .beads/issues.jsonl
   bd ready
   ```
   Report created/updated IDs, skipped duplicates, wired dependencies (including cross-links to existing beads), and the resulting `bd ready` queue.
