---
name: atomic-conventional-c4-commits
description: >-
  Decompose git status and diffs into minimal, bisectable atomic commits
  combining Conventional Commits (v1.0.0) semantic types with ZeroMQ C4
  (RFC 42) discipline. Use when asked to commit changes, split diffs into
  atomic patches, stage hunks with git add -p, or write Conventional Commit
  messages (<= 50 char imperative headline, 72 char body).
---

# Skill: Atomic Conventional C4 Commits

## Role & Purpose
Inspect git status and diffs, isolate them into strict minimal patches solving exactly one problem, and generate clean, bisectable commits combining Conventional Commits (v1.0.0) semantic types with ZeroMQ C4 (RFC 42) brevity and discipline.

---

## Operating Principles (ZeroMQ C4 Rules)
1. **Single Minimal Patch:** Each commit must solve exactly one isolated problem or introduce one minimal feature. Never bundle cleanup/formatting with behavioral changes.
2. **Bisect & Build Invariant:** Every atomic commit must compile cleanly and pass existing tests on its own. Breaking builds across commits is forbidden.
3. **No Mixed Intents:** If a task requires refactoring before implementing a feature, split it: commit 1 (`refactor`), commit 2 (`feat`).

---

## Procedure

1. **State Discovery**
   - Run `git status -s` to inspect modified, staged, and untracked files.
   - Guard against untracked runtime artifacts, `.env` files, credentials, or accidental lockfile noise.

2. **Decomposition & Hunk Staging**
   - Group files and individual diff hunks by singular intent.
   - Use targeted staging (`git add <file...>` or interactive `git add -p`).
   - Strip unrelated whitespace adjustments or reformatting from functional diffs.

3. **Validation Pass**
   - Confirm staged changes address only the stated problem/intent.
   - Ensure repository stability at this commit boundary.

4. **Message Formatting (Conventional + C4)**
   - **Line 1 (Headline):** `<type>(<optional scope>): <imperative summary>`
     - Hard limit: **<= 50 characters**.
     - Imperative, present tense (`add`, not `added` / `adds`).
     - Lowercase first letter; no trailing period.
     - Breaking change indicated by `!` before `:` (e.g., `feat(api)!: drop v1 endpoints`).
   - **Line 2:** Blank line.
   - **Line 3+ (Body, optional):** Concise problem-solution context wrapped at **72 characters**. Reference issue/ticket if applicable (`Fixes #123`).

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
   - Commit cleanly:
     - Single-line: `git commit -m "<type>(<scope>): <summary>"`
     - With body: `git commit -m "<type>(<scope>): <summary>" -m "<problem-solution body>"`
