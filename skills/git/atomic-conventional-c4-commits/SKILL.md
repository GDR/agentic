---
name: atomic-conventional-c4-commits
description: >-
  Decompose git status and diffs into minimal, bisectable atomic commits
  combining Conventional Commits (v1.0.0) semantic types with ZeroMQ C4
  (RFC 42) discipline. Use when asked to commit changes, split diffs into
  atomic patches, stage hunks with git add -p, or write Conventional Commit
  messages (<= 50 char imperative headline and mandatory 72-char wrapped
  Problem:/Solution: body).
---

# Skill: Atomic Conventional C4 Commits

## Role & Purpose
Inspect git status and diffs, isolate them into strict minimal patches solving exactly one problem, and generate clean, bisectable commits combining Conventional Commits (v1.0.0) semantic types with ZeroMQ C4 (RFC 42) brevity and discipline.

---

## Operating Principles (ZeroMQ C4 Rules)
1. **Single Minimal Patch:** Each commit must solve exactly one isolated problem or introduce one minimal feature. Never bundle cleanup/formatting with behavioral changes.
2. **Bisect & Build Invariant:** Order commits by dependency so every commit boundary compiles and passes tests on its own without breaking intermediate builds. (See Validation Pass for when to run heavy checks so ordering does not trigger redundant N× full-suite loops.)
3. **No Mixed Intents:** If a task requires refactoring before implementing a feature, split it: commit 1 (`refactor`), commit 2 (`feat`).

---

## Procedure

1. **State Discovery (Fast & Scoped)**
   - Run a single `git status -s`, `git diff --stat`, and `git diff --cached --stat` (plus `git worktree list` if worktree mismatch is suspected).
   - If the current worktree is clean while pending changes live in another checkout/worktree, ask the user once immediately where to commit before reading diffs.
   - Inspect only the changed diffs needed to group commits and draft messages; do **not** read unrelated/untouched repository files (other hosts, overlays, full test suites, or baseline `HEAD:` files).
   - Guard against untracked runtime artifacts, `.env` files, credentials, or accidental lockfile noise.

2. **Decomposition & Hunk Staging**
   - Group files and individual diff hunks by singular intent, ordered from base dependencies upward.
   - Use targeted staging (`git add <file...>` or interactive `git add -p`).
   - Strip unrelated whitespace adjustments or reformatting from functional diffs.

3. **Validation Pass**
   - Confirm staged changes address only the stated problem/intent.
   - Run fast per-commit hooks (`pre-commit`/linters) on each commit — never bypass with `--no-verify`.
   - Run heavy repo-wide build/test suites (e.g., `nix flake check`, full CI/test suites) **at most once on final `HEAD`** (or skip if the identical tree SHA was already verified), **not** in a per-commit loop — unless the user explicitly asks to verify every bisect boundary or a file was split across commits via `git add -p`.

4. **Message Formatting (Conventional + C4)**
   - **Line 1 (Headline):** `<type>(<optional scope>): <imperative summary>`
     - Hard limit: **<= 50 characters**.
     - Imperative, present tense (`add`, not `added` / `adds`).
     - Lowercase first letter; no trailing period.
     - Breaking change indicated by `!` before `:` (e.g., `feat(api)!: drop v1 endpoints`).
   - **Line 2:** Blank line.
   - **Line 3+ (Mandatory Body — ZeroMQ C4 RFC 42 §2.3):** Never emit single-line commits. Always include both labeled paragraphs wrapped at **72 characters**:
     - `Problem: <what is broken, missing, or motivates the patch>`
     - Blank line
     - `Solution: <minimal concrete change solving the problem>`
     - Optional footer block after a blank line (`Fixes #123`, `BREAKING CHANGE: ...`).

   ```text
   fix(hooks): gate git commit on skill read

   Problem: Agents invoke git commit without reading the commit skill,
   producing non-atomic commits and inconsistent messages.

   Solution: Add a PreToolUse hook that denies git commit until the
   session transcript shows the commit skill was read.
   ```

   ### Allowed Types:
   - `feat`: New feature or user-facing capability
   - `fix`: Bug fix
   - `refactor`: Structural rewrite without behavioral or API changes
   - `style`: Formatting, whitespace, linting fixes (zero logic change)
   - `perf`: Performance or memory optimization
   - `test`: Adding or correcting tests
   - `build`: Build system, toolchain, or external dependency bumps
   - `chore`: Auxiliary tooling, configuration, scripts
   - `docs`: Documentation updates only

5. **Execution**
   - Batch multi-commit sequences into a single shell command (and a single `nix develop --command` session when hooks require devShell tools) rather than separate turns per commit.
   - Scope staging strictly to intended files so unrelated unstaged edits do not trigger abort/re-plan cycles.
   - Commit cleanly (Git separates multiple `-m` flags with blank lines):
     - Standard: `git commit -m "<type>(<scope>): <summary>" -m "Problem: <...>" -m "Solution: <...>"`
     - With footer: `git commit -m "<type>(<scope>): <summary>" -m "Problem: <...>" -m "Solution: <...>" -m "Fixes #123"`
