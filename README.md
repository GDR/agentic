# agentic

Canonical, OS-agnostic repository for cross-tool [Agent Skills](https://agentskills.io) and shared agentic artifacts.

## Repository Structure

```text
.
├── skills/                 # Canonical Agent Skills (skills/<category>/<skill>/SKILL.md)
│   ├── design/             # UI/UX, anti-slop, shadcn, and macOS/HIG skills
│   ├── git/                # Git workflow and commit discipline skills
│   └── security/           # Security audit, PR review, static analysis, fuzzing, and desktop hardening skills
│       └── <skill-name>/
│           ├── SKILL.md    # Required: YAML frontmatter (name, description) + markdown body
│           ├── scripts/    # Optional helper executables
│           ├── references/ # Optional on-demand documentation
│           └── assets/     # Optional templates or static assets
├── skills.json             # Antigravity inherits manifest listing category directories
├── rules/
│   └── AGENTS.md           # Canonical global rules symlinked across AI harnesses
├── hooks/
│   ├── commit_skill_gate.py      # PreToolUse gate requiring commit skill read
│   └── test_commit_skill_gate.py # Stdlib unittest suite for commit_skill_gate.py
├── agents/                 # Reserved for future cross-tool agent definitions
├── commands/               # Reserved for future cross-tool commands
├── scripts/
│   ├── upstream.py         # Commit-SHA and SHA-256 pinned upstream skill vendoring
│   └── validate.py         # Skill structure, frontmatter, category, and skills.json validator
├── upstream.json           # Pinned upstream repos, 40-char commit SHAs, and file hashes
├── flake.nix               # Nix flake (devShell, formatter, skills package, validate/verify checks)
└── justfile                # Task runner recipes (new, validate, verify-upstream, sync/bump, check)
```

## Authoring & Validation

Enter the development shell (or prefix commands with `nix develop -c`):

```bash
nix develop
```

Common workflows:

```bash
just new <cat>/<name>   # Scaffold skills/<category>/<name>/SKILL.md from template
just validate            # Run scripts/validate.py against skills/ and skills.json
just verify-upstream     # Offline SHA-256 verification of vendored upstream files
just test-hooks          # Run hook unit tests under hooks/
just sync-upstream       # Fetch pinned upstream commits and assert recorded hashes
just bump-upstream       # Resolve latest upstream HEAD SHAs locally for git diff review
just check               # Run validate, verify-upstream, test-hooks, and nix flake check
just fmt                 # Format Nix files via nix fmt (nixfmt-tree)
```

You can also run Nix commands directly:

```bash
nix flake check               # Run validate-skills and verify-upstream checks
nix build .#skills            # Build packages.<system>.skills output
nix fmt                       # Format Nix files
```

> **Note:** `nix flake check` evaluates Git-tracked files only. After scaffolding a new skill with `just new <cat>/<name>`, stage it with `git add skills/<cat>/<name>` before running `nix flake check` or `just check`. When adding a new category under `skills/`, register `~/Workspaces/gdr/agentic/skills/<cat>` in [`skills.json`](skills.json) and add it to `watchSubpaths` in `GDR/dot`.

## Supply-Chain Pinning (`upstream.json`)

Third-party skills and rules are never pulled blindly from floating branches at runtime:

- `upstream.json` pins each upstream repository to an immutable 40-character commit SHA (`rev`) and records the SHA-256 digest of every vendored file (`files`).
- `nix flake check` runs `scripts/upstream.py verify` completely offline inside the Nix sandbox, catching missing, modified, symlinked, or unrecorded files in vendored directories.
- Bumping upstream dependencies is an explicit manual step (`just bump-upstream [source]`) that prints the GitHub `compare` URL and updates `upstream.json` locally so you can audit `git diff` before committing.

## Validation Rules

`scripts/validate.py` checks every skill under `skills/` (flat or 1-level category directories `skills/<category>/<skill>/`):

- `SKILL.md` exists and starts with valid YAML frontmatter (`---` ... `---`).
- `name` matches the leaf directory name, is unique across all categories, is 1–64 characters long, and matches `^[a-z0-9]+(-[a-z0-9]+)*$`.
- `description` is non-empty and at most 1024 characters.
- Relative Markdown links in the body resolve inside the skill directory and point to existing files.
- [`skills.json`](skills.json) registers every category directory under `skills/`.

## Global Rules

[`rules/AGENTS.md`](rules/AGENTS.md) is the canonical cross-harness global rules file, symlinked via `GDR/dot` (`detached-repos`) to `~/.gemini/config/AGENTS.md`, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`, and `~/.gemini/GEMINI.md`.

## Hooks

[`hooks/commit_skill_gate.py`](hooks/commit_skill_gate.py) is a `PreToolUse` gate for Antigravity (`run_command`) and Claude Code (`Bash`) that blocks `git commit` until `atomic-conventional-c4-commits/SKILL.md` has been read or loaded in the active conversation transcript.

## Included Skills (`62`)

### Authored Skills (`git/`, `design/`, & `security/`)
- [`atomic-conventional-c4-commits`](skills/git/atomic-conventional-c4-commits/SKILL.md) — Decompose diffs into minimal, bisectable patches formatted with Conventional Commits v1.0.0 and ZeroMQ C4 discipline.
- [`design-pipeline`](skills/design/design-pipeline/SKILL.md) — Generate, audit, and refactor UI/UX components with anti-slop constraints, markup pruning rules, heuristic QA (including vendored [`signs-of-ai-design.md`](skills/design/design-pipeline/references/signs-of-ai-design.md)), and visual asset cleanup pipelines.
- [`macos-native-design`](skills/design/macos-native-design/SKILL.md) — Enforce Apple HIG and native macOS desktop conventions (window chrome, split views, menu bars/shortcuts, vibrancy, SF Symbols) and route to vendored HIG skills.
- [`desktop-audit`](skills/security/desktop-audit/SKILL.md) — Audit desktop-specific OS, IPC, updater, and local privilege boundaries across Electron, Tauri, and native C++/Rust apps.

### Pinned Upstream Skills (`design/`, 6 Upstream Sources)
- [`antislop`](skills/design/antislop/SKILL.md), [`antislop-ui`](skills/design/antislop-ui/SKILL.md), [`antislop-human`](skills/design/antislop-human/SKILL.md), [`antislop-layoutmobile`](skills/design/antislop-layoutmobile/SKILL.md), [`antislop-copywriting`](skills/design/antislop-copywriting/SKILL.md), [`antislop-code`](skills/design/antislop-code/SKILL.md) — From `miqdadbadjuber/anti-slop` (MIT).
- [`unslop-ui`](skills/design/unslop-ui/SKILL.md) — From `felipebasurto/unslop-ui` (MIT).
- [`shadcn`](skills/design/shadcn/SKILL.md) — From `shadcn-ui/ui` (MIT).
- [`macos-design-guidelines`](skills/design/macos-design-guidelines/SKILL.md) — From `ehmo/platform-design-skills` (`skills/macos`, MIT).
- [`apple-design-hig`](skills/design/apple-design-hig/SKILL.md) — From `mr8lu/apple-design-hig` (`skills/apple-design-hig`).

### Pinned Upstream Skills (`security/`, 7 Upstream Sources)
- [`security-audit`](skills/security/security-audit/SKILL.md) — From `cloudflare/security-audit-skill` (MIT).
- [`security-review`](skills/security/security-review/SKILL.md) — From `wioui/security-review-skill` (MIT).
- [`owasp-security`](skills/security/owasp-security/SKILL.md) — From `agamm/claude-code-owasp` (MIT).
- [`snyk-fix`](skills/security/snyk-fix/SKILL.md) — From `snyk/studio-recipes` (`command_directives/synchronous_remediation/skills/snyk-fix`, Apache-2.0).
- [`tauri`](skills/security/tauri/SKILL.md), [`electron`](skills/security/electron/SKILL.md) — From `ericrisco/rsc-harness` (MIT).
- [`tauri-security`](skills/security/tauri-security/SKILL.md), [`tauri-framework-security`](skills/security/tauri-framework-security/SKILL.md) — From `full-stack-skills/tauri-skills` (Apache-2.0).
- From `trailofbits/skills` (CC-BY-SA-4.0):
  - Core & static analysis (10): [`audit-context-building`](skills/security/audit-context-building/SKILL.md), [`fp-check`](skills/security/fp-check/SKILL.md), [`sharp-edges`](skills/security/sharp-edges/SKILL.md), [`variant-analysis`](skills/security/variant-analysis/SKILL.md), [`supply-chain-risk-auditor`](skills/security/supply-chain-risk-auditor/SKILL.md), [`codeql`](skills/security/codeql/SKILL.md), [`semgrep`](skills/security/semgrep/SKILL.md), [`sarif-parsing`](skills/security/sarif-parsing/SKILL.md), [`burpsuite-project-parser`](skills/security/burpsuite-project-parser/SKILL.md), [`constant-time-analysis`](skills/security/constant-time-analysis/SKILL.md).
  - Testing handbook (15): [`address-sanitizer`](skills/security/address-sanitizer/SKILL.md), [`aflpp`](skills/security/aflpp/SKILL.md), [`atheris`](skills/security/atheris/SKILL.md), [`cargo-fuzz`](skills/security/cargo-fuzz/SKILL.md), [`constant-time-testing`](skills/security/constant-time-testing/SKILL.md), [`coverage-analysis`](skills/security/coverage-analysis/SKILL.md), [`fuzzing-dictionary`](skills/security/fuzzing-dictionary/SKILL.md), [`fuzzing-obstacles`](skills/security/fuzzing-obstacles/SKILL.md), [`harness-writing`](skills/security/harness-writing/SKILL.md), [`libafl`](skills/security/libafl/SKILL.md), [`libfuzzer`](skills/security/libfuzzer/SKILL.md), [`ossfuzz`](skills/security/ossfuzz/SKILL.md), [`ruzzy`](skills/security/ruzzy/SKILL.md), [`testing-handbook-generator`](skills/security/testing-handbook-generator/SKILL.md), [`wycheproof`](skills/security/wycheproof/SKILL.md).
  - Trailmark graph & taint analysis (15): [`audit-augmentation`](skills/security/audit-augmentation/SKILL.md), [`crypto-protocol-diagram`](skills/security/crypto-protocol-diagram/SKILL.md), [`diagramming-code`](skills/security/diagramming-code/SKILL.md), [`genotoxic`](skills/security/genotoxic/SKILL.md), [`graph-evolution`](skills/security/graph-evolution/SKILL.md), [`mermaid-to-proverif`](skills/security/mermaid-to-proverif/SKILL.md), [`slicing-code-context`](skills/security/slicing-code-context/SKILL.md), [`taint-trace`](skills/security/taint-trace/SKILL.md), [`trailmark`](skills/security/trailmark/SKILL.md), [`trailmark-finding-triage`](skills/security/trailmark-finding-triage/SKILL.md), [`trailmark-review-gate`](skills/security/trailmark-review-gate/SKILL.md), [`trailmark-structural`](skills/security/trailmark-structural/SKILL.md), [`trailmark-summary`](skills/security/trailmark-summary/SKILL.md), [`trailmark-variant-neighborhood`](skills/security/trailmark-variant-neighborhood/SKILL.md), [`vector-forge`](skills/security/vector-forge/SKILL.md).
