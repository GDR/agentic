# Beads (`bd`) Task Tracking

- Find unblocked work with `bd ready` (or `bd ready --json`) before picking a task.
- Claim a bead before editing code: `bd update <id> --claim` (or `bd update <id> --status in_progress`).
- Never bury discovered bugs, regressions, or follow-ups in chat—file them as beads:
  `bd create "<title>" -t <bug|feature|task|epic> -p <0..4> -d "<details>"` and link with `bd dep add <id> <blocker-id>`.
- When creating new beads, check existing active beads (`bd list --status open,in_progress,blocked --json`) and wire blockers/links in both directions (`bd dep add`, `bd dep relate`).
- Close finished work with `bd close <id> --reason "<commit or summary>"` (export `.beads/issues.jsonl` only on `main`, not on parallel bead branches).
- **Multi-worktree safety**:
  - Set a unique actor per worktree/agent (`BEADS_ACTOR=<branch-or-agent>` or `--actor <name>`).
  - Use atomic claiming (`bd update <id> --claim` or `--if-status open --status in_progress --assignee "$BEADS_ACTOR"`); exit code 13 means another agent claimed it—pick the next `bd ready` item.
  - Never pass `--force` to steal another live actor's `in_progress` claim (use `bd reclaim` only for dead/stale leases).
