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
├── rules/
│   └── AGENTS.md           # Canonical global rules symlinked across AI harnesses
├── hooks/
│   ├── commit_skill_gate.py      # PreToolUse gate requiring commit skill read
│   ├── merge_claude_hooks.py     # Idempotent ~/.claude/settings.json hook merger
│   ├── test_commit_skill_gate.py # Stdlib unittest suite for commit_skill_gate.py
│   └── test_merge_claude_hooks.py# Stdlib unittest suite for merge_claude_hooks.py
├── mcp/
│   ├── global.json               # Portable, secret-free global MCP server definitions
│   ├── sync.py                   # Cross-harness project-local MCP generator & stdio wrapper
│   └── test_sync.py              # Stdlib unittest suite for mcp/sync.py and mcp/global.json
├── beads/
│   ├── rule.md                   # Always-on Beads rule synced into consumer projects (.agents/rules/beads.md)
│   ├── sync.py                   # Idempotent shellHook sync for rule.md and .git/info/exclude
│   ├── ui.py                     # Zero-dependency local Kanban + SVG dependency-graph Web GUI
│   └── test_beads.py             # Stdlib unittest suite for beads/sync.py and beads/ui.py
├── nix/
│   ├── beads.nix                 # Flake helpers lib.mkBeads and lib.mkBeadsUi (beads-ui package)
│   ├── home-manager.nix          # Home Manager module (programs.agentic) for harness wiring
│   ├── layout.nix                # Auto-discovered skillCategories, watchSubpaths, fanout, links
│   └── mcp.nix                   # Flake helper lib.mkMcp and server presets (nixos, ghidra)
├── agents/                 # Reserved for future cross-tool agent definitions
├── commands/               # Reserved for future cross-tool commands
├── scripts/
│   ├── upstream.py         # Commit-SHA and SHA-256 pinned upstream skill vendoring
│   └── validate.py         # Skill structure, frontmatter, and category validator
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
just validate            # Run scripts/validate.py against skills/
just verify-upstream     # Offline SHA-256 verification of vendored upstream files
just test-hooks          # Run hook unit tests under hooks/
just test-mcp            # Run MCP sync unit tests and validate mcp/global.json
just sync-upstream       # Fetch pinned upstream commits and assert recorded hashes
just bump-upstream       # Resolve latest upstream HEAD SHAs locally for git diff review
just check               # Run validate, verify-upstream, test-hooks, test-mcp, and nix flake check
just fmt                 # Format Nix files via nix fmt (nixfmt-tree)
```

You can also run Nix commands directly:

```bash
nix flake check               # Run validate-skills and verify-upstream checks
nix build .#skills            # Build packages.<system>.skills output
nix fmt                       # Format Nix files
```

> **Note:** `nix flake check` evaluates Git-tracked files only. After scaffolding a new skill with `just new <cat>/<name>`, stage it with `git add skills/<cat>/<name>` before running `nix flake check` or `just check`. `nix/layout.nix` auto-discovers categories under `skills/`, so after adding a new category update the `agentic` flake input in consumer repositories (e.g. `GDR/dot`).

## Supply-Chain Pinning (`upstream.json`)

Third-party skills and rules are never pulled blindly from floating branches at runtime:

- `upstream.json` pins each upstream repository to an immutable 40-character commit SHA (`rev`) and records the SHA-256 digest of every vendored file (`files`).
- `scripts/upstream.py` deterministically aligns vendored `SKILL.md` frontmatter `name:` with the prefixed destination folder name before hashing.
- `nix flake check` runs `scripts/upstream.py verify` completely offline inside the Nix sandbox, catching missing, modified, symlinked, or unrecorded files in vendored directories.
- Bumping upstream dependencies is an explicit manual step (`just bump-upstream [source]`) that prints the GitHub `compare` URL and updates `upstream.json` locally so you can audit `git diff` before committing.

## Validation Rules

`scripts/validate.py` checks every skill under `skills/` (flat or 1-level category directories `skills/<category>/<skill>/`):

- `SKILL.md` exists and starts with valid YAML frontmatter (`---` ... `---`).
- Skills inside category directories (`skills/<category>/<skill>/`) must be prefixed with `<category>-`.
- `name` matches the leaf directory name, is unique across all categories, is 1–64 characters long, and matches `^[a-z0-9]+(-[a-z0-9]+)*$`.
- `description` is non-empty and at most 1024 characters.
- Relative Markdown links in the body resolve inside the skill directory and point to existing files.

## Global Rules

[`rules/AGENTS.md`](rules/AGENTS.md) is the canonical cross-harness global rules file, symlinked via `lib.layout.links` (consumed by `GDR/dot` `detached-repos`) to `~/.gemini/config/AGENTS.md`, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`, and `~/.gemini/GEMINI.md`.

## Hooks & Home Manager Module

[`hooks/commit_skill_gate.py`](hooks/commit_skill_gate.py) is a `PreToolUse` gate for Antigravity (`run_command`) and Claude Code (`Bash`) that blocks `git commit` until `git-commit-branch/SKILL.md` has been read or loaded in the active conversation transcript.

The flake exports:
- `lib.layout`: Auto-discovered `skillCategories`, `watchSubpaths`, `fanout`, and `links` describing this repository's directory layout.
- `homeManagerModules.default` (`programs.agentic`): Standalone Home Manager module accepting `enable`, `repoPath`, and `skillCategories`. Writes `~/.gemini/config/skills.json`, `~/.gemini/config/hooks.json`, and merges the Claude `PreToolUse` gate into `~/.claude/settings.json` via [`hooks/merge_claude_hooks.py`](hooks/merge_claude_hooks.py).

## Quick Start: Connecting Everything

1. **Global (Home Manager — once per machine):** Enables global skills (`skills/*`), global rules (`rules/AGENTS.md`), and the `git commit` skill gate across harnesses:

```nix
# In your NixOS / Home Manager flake:
{
  inputs.agentic.url = "github:GDR/agentic";
  # ...
  imports = [ inputs.agentic.homeManagerModules.default ];
  programs.agentic = {
    enable = true;
    # repoPath = "Workspaces/gdr/agentic"; # default
  };
}
```

2. **Per-project (`flake.nix` + `.envrc` + `justfile`):** Embeds project-local MCP servers (`lib.mkMcp`) and Beads task tracking + local Web GUI (`lib.mkBeads`):

```nix
# flake.nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    agentic.url = "github:GDR/agentic";
  };

  outputs =
    { nixpkgs, agentic, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      mcp = agentic.lib.mkMcp {
        inherit pkgs;
        servers = {
          nixos = agentic.lib.mcp.nixos { inherit pkgs; };
          # ghidra = agentic.lib.mcp.ghidra { url = "http://127.0.0.1:8089"; };
          # rea = agentic.lib.mcp.rea { inherit pkgs; };
        };
      };

      beads = agentic.lib.mkBeads {
        inherit pkgs;
        # Optional: autoInit = true; syncRule = true; excludeGit = true; defaultPort = 7474;
      };
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = [ pkgs.just ] ++ mcp.packages ++ beads.packages;
        shellHook = ''
          ${mcp.shellHook}
          ${beads.shellHook}
        '';
      };
    };
}
```

```bash
# .envrc
use flake
```

```just
# justfile
[doc('Start local Beads Web GUI on 127.0.0.1')]
[positional-arguments]
tasks *args:
    @beads-ui "$@"
```

3. **Initialize & launch in the consumer project:**

```bash
direnv allow                                                                      # or: nix develop
bd init --non-interactive --skip-agents --skip-hooks && bd config set export.auto true
just tasks                                                                        # http://127.0.0.1:7474
```

> Both shell hooks are idempotent, locally exclude generated files via `.git/info/exclude` (worktree-safe), and can be disabled with `AGENTIC_MCP_DISABLE=1` / `AGENTIC_BEADS_DISABLE=1`.

## MCP Servers

MCP definitions are split into two tiers:

1. **Global (`mcp/global.json`):** Portable, secret-free servers active across workspaces (`context7`).
2. **Project-local (`lib.mkMcp` via `flake.nix` + `direnv`):** Per-repository servers synced automatically on `nix develop` / `direnv allow` into local harness configs (`.agents/mcp_config.json`, `.mcp.json`, and optionally `.codex/config.toml`, `opencode.json`, `.gemini/settings.json`; override via `harnesses = agentic.lib.mcp.allHarnesses` or `AGENTIC_MCP_HARNESSES=all`) and excluded locally via `.git/info/exclude`.

### Token Storage & Least-Privilege Injection

Never commit tokens to `agentic`, project repositories, or Nix `/nix/store` evaluations:

- **Global user tokens:** `${XDG_CONFIG_HOME:-~/.config}/agentic/env` (`0600`, `KEY=VALUE`)
- **Per-project tokens:** gitignored `.agents/mcp.env` (override via `projectEnvFile`)
- **Precedence:** global file < project file < process environment
- **Stdio secrets (`secretEnv = [ "VAR" ]`):** [`mcp/sync.py`](mcp/sync.py) generates a `0700` wrapper in `.agents/.mcp-wrappers/<name>` that injects only whitelisted variables before `exec` without storing secrets in harness JSON.
- **HTTP auth (`bearerTokenEnvVar` / `secretHeaders`):** Claude Code (`${VAR}`), Codex (`bearer_token_env_var` / `env_http_headers`), OpenCode (`{env:VAR}`), and Gemini CLI (`${VAR}`) read env vars natively; for Antigravity, prefer OAuth when supported or let `sync.py` resolve headers into `0600` `.agents/mcp_config.json`.

## Embeddable Beads (`lib.mkBeads`)

[`nix/beads.nix`](nix/beads.nix) exports `lib.mkBeads` and `packages.<system>.beads-ui`:

- **`packages`:** Exposes `bd` (`pkgs.beads`) and `beads-ui` (zero-dependency local Kanban + SVG dependency-graph viewer in [`beads/ui.py`](beads/ui.py)) on `PATH`.
- **`shellHook`:** Runs [`beads/sync.py`](beads/sync.py) to sync [`beads/rule.md`](beads/rule.md) into `.agents/rules/beads.md` and `skills/beads/*` into `.agents/skills/`, add them to the common `.git/info/exclude`, and optionally initialize `.beads/` when `autoInit = true`.
- **Standalone viewer:** Run `nix run github:GDR/agentic#beads-ui` in any repository with `.beads/`.

## Included Skills (`66`)

### Authored Skills (`beads/`, `git/`, `design/`, & `security/`)
- [`beads-plan`](skills/beads/beads-plan/SKILL.md) — Convert an implementation plan, RFC, or design doc into a Beads epic and wave-ordered task DAG with `--acceptance`, bidirectional cross-links against existing beads, and `bd dep cycles` / `bd graph --open` verification.
- [`beads-triage`](skills/beads/beads-triage/SKILL.md) — Convert a brain-dump, notes file, or scout report into deduplicated Beads epics/tasks with priorities and `bd dep add` blockers.
- [`beads-work`](skills/beads/beads-work/SKILL.md) — Pick the highest-priority unblocked `bd ready` bead, atomically claim it, implement & verify, file follow-ups, and close it.
- [`git-commit-branch`](skills/git/git-commit-branch/SKILL.md) — Decompose diffs into minimal, bisectable patches formatted with Conventional Commits v1.0.0 and ZeroMQ C4 discipline.
- [`git-commit-master`](skills/git/git-commit-master/SKILL.md) — Run `git-commit-branch` on the active branch/worktree and fast-forward the primary worktree's `main`/`master` branch safely.
- [`design-pipeline`](skills/design/design-pipeline/SKILL.md) — Generate, audit, and refactor UI/UX components with anti-slop constraints, markup pruning rules, heuristic QA (including vendored [`signs-of-ai-design.md`](skills/design/design-pipeline/references/signs-of-ai-design.md)), and visual asset cleanup pipelines.
- [`design-macos-native-design`](skills/design/design-macos-native-design/SKILL.md) — Enforce Apple HIG and native macOS desktop conventions (window chrome, split views, menu bars/shortcuts, vibrancy, SF Symbols) and route to vendored HIG skills.
- [`security-desktop-audit`](skills/security/security-desktop-audit/SKILL.md) — Audit desktop-specific OS, IPC, updater, and local privilege boundaries across Electron, Tauri, and native C++/Rust apps.

### Pinned Upstream Skills (`design/`, 6 Upstream Sources)
- [`design-antislop`](skills/design/design-antislop/SKILL.md), [`design-antislop-ui`](skills/design/design-antislop-ui/SKILL.md), [`design-antislop-human`](skills/design/design-antislop-human/SKILL.md), [`design-antislop-layoutmobile`](skills/design/design-antislop-layoutmobile/SKILL.md), [`design-antislop-copywriting`](skills/design/design-antislop-copywriting/SKILL.md), [`design-antislop-code`](skills/design/design-antislop-code/SKILL.md) — From `miqdadbadjuber/anti-slop` (MIT).
- [`design-unslop-ui`](skills/design/design-unslop-ui/SKILL.md) — From `felipebasurto/unslop-ui` (MIT).
- [`design-shadcn`](skills/design/design-shadcn/SKILL.md) — From `shadcn-ui/ui` (MIT).
- [`design-macos-design-guidelines`](skills/design/design-macos-design-guidelines/SKILL.md) — From `ehmo/platform-design-skills` (`skills/macos`, MIT).
- [`design-apple-design-hig`](skills/design/design-apple-design-hig/SKILL.md) — From `mr8lu/apple-design-hig` (`skills/apple-design-hig`).

### Pinned Upstream Skills (`security/`, 7 Upstream Sources)
- [`security-audit`](skills/security/security-audit/SKILL.md) — From `cloudflare/security-audit-skill` (MIT).
- [`security-review`](skills/security/security-review/SKILL.md) — From `wioui/security-review-skill` (MIT).
- [`security-owasp-security`](skills/security/security-owasp-security/SKILL.md) — From `agamm/claude-code-owasp` (MIT).
- [`security-snyk-fix`](skills/security/security-snyk-fix/SKILL.md) — From `snyk/studio-recipes` (`command_directives/synchronous_remediation/skills/snyk-fix`, Apache-2.0).
- [`security-tauri`](skills/security/security-tauri/SKILL.md), [`security-electron`](skills/security/security-electron/SKILL.md) — From `ericrisco/rsc-harness` (MIT).
- [`security-tauri-security`](skills/security/security-tauri-security/SKILL.md), [`security-tauri-framework-security`](skills/security/security-tauri-framework-security/SKILL.md) — From `full-stack-skills/tauri-skills` (Apache-2.0).
- From `trailofbits/skills` (CC-BY-SA-4.0):
  - Core & static analysis (10): [`security-audit-context-building`](skills/security/security-audit-context-building/SKILL.md), [`security-fp-check`](skills/security/security-fp-check/SKILL.md), [`security-sharp-edges`](skills/security/security-sharp-edges/SKILL.md), [`security-variant-analysis`](skills/security/security-variant-analysis/SKILL.md), [`security-supply-chain-risk-auditor`](skills/security/security-supply-chain-risk-auditor/SKILL.md), [`security-codeql`](skills/security/security-codeql/SKILL.md), [`security-semgrep`](skills/security/security-semgrep/SKILL.md), [`security-sarif-parsing`](skills/security/security-sarif-parsing/SKILL.md), [`security-burpsuite-project-parser`](skills/security/security-burpsuite-project-parser/SKILL.md), [`security-constant-time-analysis`](skills/security/security-constant-time-analysis/SKILL.md).
  - Testing handbook (15): [`security-address-sanitizer`](skills/security/security-address-sanitizer/SKILL.md), [`security-aflpp`](skills/security/security-aflpp/SKILL.md), [`security-atheris`](skills/security/security-atheris/SKILL.md), [`security-cargo-fuzz`](skills/security/security-cargo-fuzz/SKILL.md), [`security-constant-time-testing`](skills/security/security-constant-time-testing/SKILL.md), [`security-coverage-analysis`](skills/security/security-coverage-analysis/SKILL.md), [`security-fuzzing-dictionary`](skills/security/security-fuzzing-dictionary/SKILL.md), [`security-fuzzing-obstacles`](skills/security/security-fuzzing-obstacles/SKILL.md), [`security-harness-writing`](skills/security/security-harness-writing/SKILL.md), [`security-libafl`](skills/security/security-libafl/SKILL.md), [`security-libfuzzer`](skills/security/security-libfuzzer/SKILL.md), [`security-ossfuzz`](skills/security/security-ossfuzz/SKILL.md), [`security-ruzzy`](skills/security/security-ruzzy/SKILL.md), [`security-testing-handbook-generator`](skills/security/security-testing-handbook-generator/SKILL.md), [`security-wycheproof`](skills/security/security-wycheproof/SKILL.md).
  - Trailmark graph & taint analysis (15): [`security-audit-augmentation`](skills/security/security-audit-augmentation/SKILL.md), [`security-crypto-protocol-diagram`](skills/security/security-crypto-protocol-diagram/SKILL.md), [`security-diagramming-code`](skills/security/security-diagramming-code/SKILL.md), [`security-genotoxic`](skills/security/security-genotoxic/SKILL.md), [`security-graph-evolution`](skills/security/security-graph-evolution/SKILL.md), [`security-mermaid-to-proverif`](skills/security/security-mermaid-to-proverif/SKILL.md), [`security-slicing-code-context`](skills/security/security-slicing-code-context/SKILL.md), [`security-taint-trace`](skills/security/security-taint-trace/SKILL.md), [`security-trailmark`](skills/security/security-trailmark/SKILL.md), [`security-trailmark-finding-triage`](skills/security/security-trailmark-finding-triage/SKILL.md), [`security-trailmark-review-gate`](skills/security/security-trailmark-review-gate/SKILL.md), [`security-trailmark-structural`](skills/security/security-trailmark-structural/SKILL.md), [`security-trailmark-summary`](skills/security/security-trailmark-summary/SKILL.md), [`security-trailmark-variant-neighborhood`](skills/security/security-trailmark-variant-neighborhood/SKILL.md), [`security-vector-forge`](skills/security/security-vector-forge/SKILL.md).
