---
name: beads-work
description: >-
  Pick the highest-priority unblocked bead from bd ready (or a user-specified ID),
  atomically claim it, implement and verify the fix, file discovered follow-up beads,
  and close the completed bead. Use when executing tasks tracked in Beads (.beads/).
---

# Beads Work

Execute one unblocked Beads task end-to-end with safe multi-worktree claiming and clean closure.

## Workflow

1. **Select the bead**:
   - If the user provided a bead ID, inspect it with `bd show <id> --json`.
   - Otherwise query unblocked work:
     ```bash
     bd ready --json
     ```
   - Pick the highest-priority (lowest `priority` number) actionable leaf bead (`bug`, `feature`, `task`, `chore`), skipping `epic` containers unless explicitly requested.

2. **Atomically claim before editing code**:
   Set a unique actor for your worktree/session if not already set, then claim:
   ```bash
   ACTOR="${BEADS_ACTOR:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo agent)}"
   bd --actor "$ACTOR" update <id> --claim
   ```
   - If `--claim` fails (or `--if-status open` exits 13), another agent already claimed it—do **not** pass `--force`; return to `bd ready` and pick the next item.

3. **Implement and verify**:
   - Inspect full context (`bd show <id>` and parent epic if present).
   - Implement the smallest clean change that satisfies the bead's description and acceptance criteria.
   - Run the repository's build/test/lint checks (e.g., `just check`) and confirm they pass.

4. **File discovered follow-ups**:
   Never leave newly discovered bugs, regressions, or tech debt only in chat:
   ```bash
   NEW_ID=$(bd create "<title>" -t <bug|task|feature> -p <0..4> -d "<details>" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
   bd dep add "$NEW_ID" <id> -t discovered-from
   ```
   If the discovered issue blocks closing the current bead, link it with `bd dep add <id> "$NEW_ID"` and mark `<id>` blocked (`bd update <id> --status blocked`) instead of closing.

5. **Close and export**:
   ```bash
   bd close <id> --reason "<commit hash or concise verification summary>"
   bd export -o .beads/issues.jsonl
   ```
   Report the closed bead ID, verification scope, any newly filed follow-up beads, and the next `bd ready` item.
