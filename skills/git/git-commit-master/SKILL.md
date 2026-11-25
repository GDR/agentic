---
name: git-commit-master
description: >-
  Create atomic Conventional C4 commits via git-commit-branch
  and fast-forward the primary worktree's master/main branch to match. Use when
  committing from a linked worktree or feature branch and landing directly onto
  the local default branch.
---

# Skill: Commit and Land on Default Branch

## Role & Purpose
Create minimal, bisectable commits using `git-commit-branch`, then safely fast-forward the repository's local default branch (`main` or `master`) — including when working inside a linked git worktree where `git checkout master` is forbidden by Git.

---

## Procedure

1. **Commit Pending Changes via C4 Skill**
   - Check `git status --porcelain` and `git worktree list --porcelain`.
   - If the current worktree has pending changes, read/load `git-commit-branch/SKILL.md` (satisfies the `PreToolUse` commit gate) and execute it in full to create atomic commits on the current branch.
   - If the current worktree is clean:
     - If the primary worktree has uncommitted changes and the current branch is not ahead of the default branch, stop and ask the user once before touching the primary worktree.
     - If the current branch is already ahead of the default branch (`git rev-list --count "$DEFAULT_BRANCH..HEAD"` > 0), skip committing and proceed to Step 2.

2. **Resolve Worktrees and Default Branch**
   ```bash
   MAIN_WT=$(git worktree list --porcelain | awk '/^worktree /{print substr($0, 10); exit}')
   CUR_WT=$(git rev-parse --show-toplevel)
   CUR_BRANCH=$(git branch --show-current)
   ```
   - If `CUR_WT != MAIN_WT`: `DEFAULT_BRANCH=$(git -C "$MAIN_WT" branch --show-current)`.
   - If `CUR_WT == MAIN_WT`: resolve `DEFAULT_BRANCH` from `git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||'`, falling back to `main` or `master` in `refs/heads/`.

3. **Safety Guards (Stop Without Mutating on Any Failure)**
   - Require `DEFAULT_BRANCH` to be `main` or `master` (never fast-forward an unrelated branch checked out in `$MAIN_WT`).
   - If `CUR_WT == MAIN_WT` and `CUR_BRANCH == DEFAULT_BRANCH`, commits are already on `$DEFAULT_BRANCH` — stop and report.
   - Require `CUR_BRANCH` to be non-empty (stop if detached `HEAD`).
   - Require `git status --porcelain` in `$CUR_WT` to be empty.
   - If `CUR_WT != MAIN_WT`, require `git -C "$MAIN_WT" status --porcelain` to be empty.
   - Never run `git checkout "$DEFAULT_BRANCH"` inside a linked worktree.

4. **Rebase Only If `$DEFAULT_BRANCH` Moved Ahead**
   - Check `git merge-base --is-ancestor "$DEFAULT_BRANCH" HEAD`.
   - If not an ancestor, run `git rebase "$DEFAULT_BRANCH"` in `$CUR_WT`.
   - On any conflict, immediately run `git rebase --abort` and stop — report the conflict instead of resolving silently.

5. **Fast-Forward `$DEFAULT_BRANCH`**
   - If `CUR_WT != MAIN_WT`:
     ```bash
     git -C "$MAIN_WT" merge --ff-only "$CUR_BRANCH"
     ```
   - If `CUR_WT == MAIN_WT`:
     ```bash
     git checkout "$DEFAULT_BRANCH" && git merge --ff-only "$CUR_BRANCH"
     ```

6. **Verify and Report**
   - Confirm `git rev-parse HEAD` equals `git -C "$MAIN_WT" rev-parse "$DEFAULT_BRANCH"` and `git -C "$MAIN_WT" status -sb` is clean.
   - Report the landed commit hashes, headlines, and `$DEFAULT_BRANCH` path/state.

---

## Safety Boundaries
- Never bypass hooks (`--no-verify`), create merge commits (always `--ff-only`), force-overwrite history, or `git push` unless explicitly instructed.
- Never delete the active worktree or current branch unless explicitly instructed.
