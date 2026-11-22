# agentic

Canonical, OS-agnostic repository for cross-tool [Agent Skills](https://agentskills.io) and shared agentic artifacts.

## Repository Structure

```text
.
├── skills/                 # Canonical Agent Skills (skills/<category>/<skill>/SKILL.md)
│   ├── design/             # UI/UX, anti-slop, shadcn, and macOS/HIG skills
│   └── git/                # Git workflow and commit discipline skills
│       └── <skill-name>/
│           ├── SKILL.md    # Required: YAML frontmatter (name, description) + markdown body
│           ├── scripts/    # Optional helper executables
│           ├── references/ # Optional on-demand documentation
│           └── assets/     # Optional templates or static assets
├── skills.json             # Antigravity inherits manifest listing category directories
├── rules/                  # Reserved for future cross-tool rules
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
just sync-upstream       # Fetch pinned upstream commits and assert recorded hashes
just bump-upstream       # Resolve latest upstream HEAD SHAs locally for git diff review
just check               # Run validate, verify-upstream, and nix flake check
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

## Included Skills (`13`)

### Authored Skills (`git/` & `design/`)
- [`atomic-conventional-c4-commits`](skills/git/atomic-conventional-c4-commits/SKILL.md) — Decompose diffs into minimal, bisectable patches formatted with Conventional Commits v1.0.0 and ZeroMQ C4 discipline.
- [`design-pipeline`](skills/design/design-pipeline/SKILL.md) — Generate, audit, and refactor UI/UX components with anti-slop constraints, markup pruning rules, heuristic QA (including vendored [`signs-of-ai-design.md`](skills/design/design-pipeline/references/signs-of-ai-design.md)), and visual asset cleanup pipelines.
- [`macos-native-design`](skills/design/macos-native-design/SKILL.md) — Enforce Apple HIG and native macOS desktop conventions (window chrome, split views, menu bars/shortcuts, vibrancy, SF Symbols) and route to vendored HIG skills.

### Pinned Upstream Skills (`design/`, 6 Upstream Sources)
- [`antislop`](skills/design/antislop/SKILL.md), [`antislop-ui`](skills/design/antislop-ui/SKILL.md), [`antislop-human`](skills/design/antislop-human/SKILL.md), [`antislop-layoutmobile`](skills/design/antislop-layoutmobile/SKILL.md), [`antislop-copywriting`](skills/design/antislop-copywriting/SKILL.md), [`antislop-code`](skills/design/antislop-code/SKILL.md) — From `miqdadbadjuber/anti-slop` (MIT).
- [`unslop-ui`](skills/design/unslop-ui/SKILL.md) — From `felipebasurto/unslop-ui` (MIT).
- [`shadcn`](skills/design/shadcn/SKILL.md) — From `shadcn-ui/ui` (MIT).
- [`macos-design-guidelines`](skills/design/macos-design-guidelines/SKILL.md) — From `ehmo/platform-design-skills` (`skills/macos`, MIT).
- [`apple-design-hig`](skills/design/apple-design-hig/SKILL.md) — From `mr8lu/apple-design-hig` (`skills/apple-design-hig`).
