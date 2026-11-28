# Beads (`bd`) Task Tracking

- **Status lifecycle** (`bd config set status.custom "backlog:frozen,review:wip"`):
  - `backlog` (`frozen`, hidden from `bd ready`): triaged/unvetted notes and scout findings; agents must **not** claim `backlog` beads.
  - `open` (`active`, shown in `bd ready`): user-vetted "Ready to Do" queue.
  - `in_progress` (`wip`): claimed by an agent (`bd update <id> --claim`).
  - `review` (`wip`, hidden from `bd ready`, still blocks downstream dependents): verified and committed on `bead/<id>`, awaiting user review/merge.
  - `closed` (`done`): verified and landed on `main`, unblocking downstream waves.
- Find unblocked work with `bd ready` (or `bd ready --json`) before picking a task.
- Claim a bead before editing code: `bd update <id> --claim` (or `bd update <id> --status in_progress`).
- **Readable slug IDs (mandatory `--id` on every `bd create`)**: never rely on auto-generated 3-char hashes (`<prefix>-0gj`) or numeric suffixes (`.1`, `.11`):
  - Epics: `--id <prefix>-<topic>` (1–2 lowercase kebab words).
  - Child tasks: `--id <epic-id>.<short-slug>` (2–3 lowercase kebab words, total ID <= 35 chars). `bd create` rejects `--id` with `--parent`, so attach children via `--deps "parent-child:<epic-id>"`.
  - Standalone tasks: `--id <prefix>-<subsystem>-<short-slug>`.
- Never bury discovered bugs, regressions, or follow-ups in chat—file them as beads (`-s backlog` for rough/unvetted items):
  `bd create "<title>" --id <prefix>-<subsystem>-<slug> -t <bug|feature|task|epic> -p <0..4> -s backlog -d "<details>"` and link with `bd dep add <id> <blocker-id>`.
- When creating new beads, check existing active beads (`bd list --status backlog,open,in_progress,review,blocked --json`) and wire blockers/links in both directions (`bd dep add`, `bd dep relate`).
- **Commit trailer**: every git commit implementing or advancing a bead must include a `Bead: <id>` trailer at the bottom of the commit message (separated from the body by a blank line; repeat `Bead:` if a commit covers multiple beads).
- **Review handoff vs close**: once verified and committed on `bead/<id>`, move to `review` (`bd update <id> --status review` + handoff comment) instead of closing; only run `bd close <id> --reason "<commit or summary>"` when explicitly instructed to land on `main` (export `.beads/issues.jsonl` only on `main`, not on parallel bead branches).
- **Multi-worktree safety**:
  - Set a unique actor per worktree/agent (`BEADS_ACTOR=<branch-or-agent>` or `--actor <name>`).
  - Use atomic claiming (`bd update <id> --claim` or `--if-status open --status in_progress --assignee "$BEADS_ACTOR"`); exit code 13 means another agent claimed it—pick the next `bd ready` item.
  - Never pass `--force` to steal another live actor's `in_progress` claim (use `bd reclaim` only for dead/stale leases).
