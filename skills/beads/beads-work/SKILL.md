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

3. **Workspace isolation (worktrees for parallel work)**:
   - **Parallel / multi-agent runs (or when the user asks for a worktree):** Always isolate each bead in its own git worktree before editing code:
     ```bash
     bd worktree create <id> --branch "bead/<id>"
     ```
     Worktrees created via `bd worktree create` automatically share the main repo's `.beads` database via git common directory discovery. Perform all edits, tests, and commits inside that worktree.
   - **Already in a linked worktree or feature branch:** Work in place.
   - **Single sequential task on `main`/`master`:** Work in place unless the user requests a worktree or branch.

4. **Implement and verify**:
   - Inspect full context (`bd show <id>` and parent epic if present).
   - Implement the smallest clean change that satisfies the bead's description and acceptance criteria.
   - Run the repository's build/test/lint checks (e.g., `just check`) and confirm they pass.

5. **File discovered follow-ups**:
   Never leave newly discovered bugs, regressions, or tech debt only in chat:
   ```bash
   NEW_ID=$(bd create "<title>" -t <bug|task|feature> -p <0..4> -d "<details>" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
   bd dep add "$NEW_ID" <id> -t discovered-from
   ```
   If the discovered issue blocks closing the current bead, link it with `bd dep add <id> "$NEW_ID"` and mark `<id>` blocked (`bd update <id> --status blocked`) instead of closing.

6. **Commit, review handoff, and close (configurable)**:
   Follow the user's explicit preference first (`no-commit`, `commit`, `land on main`). Otherwise apply the default for the current workspace:
   - **Dedicated bead worktree or feature branch (`bead/<id>`):**
     1. Read/load `git-commit-branch/SKILL.md` and commit the verified code changes to `bead/<id>`. Do **not** export or commit `.beads/issues.jsonl` on parallel bead branches (all worktrees share the live Dolt database; committing JSONL on multiple branches causes merge conflicts).
     2. Check whether `<id>` has downstream dependents (`bd show <id> --json`, check `dependent_count > 0`):
        - **Has dependents and not yet merged to `main`:** Keep `<id>` `in_progress` and record `bd comment <id> "Ready for review on bead/<id> ($(git rev-parse --short HEAD))"` so downstream beads stay blocked until `<id>`'s code lands on `main`.
        - **No dependents (or already landed on `main`):** Close with `bd close <id> --reason "$(git rev-parse --short HEAD): <concise summary>"`.
     3. Never `git push` or merge into `main`/`master` unless explicitly instructed. When asked to land on `main`, use `git-commit-master`, then `bd close <id>` and `bd worktree remove <id>`.
   - **Primary worktree on `main`/`master` (interactive single task):**
     - Leave changes uncommitted for user review (`git diff`), and either `bd close <id> --reason "<concise summary>"` if the user wants it closed now or keep `in_progress` until committed. Refresh `.beads/issues.jsonl` (`bd export -o .beads/issues.jsonl`) only on `main` when desired.

   Report the bead ID and status, worktree/branch path (and `git diff main..bead/<id>` review command if applicable), verification scope, any newly filed follow-up beads, and the next `bd ready` item.
