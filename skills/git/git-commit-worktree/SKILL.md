---
name: git-commit-worktree
description: >-
  Create atomic Conventional C4 commits via git-commit-branch strictly inside
  the current linked git worktree without touching the primary worktree or
  default branch (main/master). Use when committing in-progress or isolated
  worktree changes on the worktree's own branch.
---

# Skill: Commit in Current Worktree

## Role & Purpose
Verify that execution is inside a linked git worktree on a non-default branch, then create minimal, bisectable commits using `git-commit-branch` without modifying the primary worktree or fast-forwarding `main`/`master`.

---

## Procedure

1. **Resolve Current Worktree & Branch**
   ```bash
   MAIN_WT=$(git worktree list --porcelain | awk '/^worktree /{print substr($0, 10); exit}')
   CUR_WT=$(git rev-parse --show-toplevel)
   CUR_BRANCH=$(git branch --show-current)
   ```

2. **Safety Guards (Stop Without Mutating on Any Failure)**
   - Require `CUR_WT != MAIN_WT`: if currently in the primary worktree, stop and report (use `git-commit-branch` or `git-commit-master` instead).
   - Require `CUR_BRANCH` to be non-empty (stop if detached `HEAD`).
   - Require `CUR_BRANCH` not to be `main` or `master`.
   - Check `git status --porcelain` in `$CUR_WT`: if clean, stop and report nothing to commit (never touch `$MAIN_WT`).

3. **Commit Pending Changes via C4 Skill**
   - Read/load `git-commit-branch/SKILL.md` (satisfies the `PreToolUse` commit gate) and execute it in full to create atomic Conventional C4 commits on `$CUR_BRANCH` inside `$CUR_WT`.

4. **Verify and Report**
   - Confirm `git status -sb` in `$CUR_WT` is clean (or report any intentionally unstaged files).
   - Report the committed hashes, headlines, `$CUR_BRANCH`, and `$CUR_WT` path.

---

## Safety Boundaries
- Never touch, merge into, or fast-forward `main`/`master` or the primary worktree (`$MAIN_WT`).
- Never bypass hooks (`--no-verify`), force-overwrite history, or `git push` unless explicitly instructed.
- Never delete or switch worktrees or branches.
