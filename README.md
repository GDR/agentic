# agentic

Canonical, OS-agnostic repository for cross-tool [Agent Skills](https://agentskills.io) and shared agentic artifacts.

## Repository Structure

```text
.
├── skills/                 # Canonical Agent Skills (skills/<name>/SKILL.md)
│   └── <skill-name>/
│       ├── SKILL.md        # Required: YAML frontmatter (name, description) + markdown body
│       ├── scripts/        # Optional helper executables
│       ├── references/     # Optional on-demand documentation
│       └── assets/         # Optional templates or static assets
├── rules/                  # Reserved for future cross-tool rules
├── agents/                 # Reserved for future cross-tool agent definitions
├── commands/               # Reserved for future cross-tool commands
├── scripts/
│   ├── upstream.py         # Commit-SHA and SHA-256 pinned upstream skill vendoring
│   └── validate.py         # Skill structure, frontmatter, and relative-link validator
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
just new <name>          # Scaffold skills/<name>/SKILL.md from template
just validate            # Run scripts/validate.py against skills/
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

> **Note:** `nix flake check` evaluates Git-tracked files only. After scaffolding a new skill with `just new <name>`, stage it with `git add skills/<name>` before running `nix flake check` or `just check`.

## Supply-Chain Pinning (`upstream.json`)

Third-party skills and rules are never pulled blindly from floating branches at runtime:

- `upstream.json` pins each upstream repository to an immutable 40-character commit SHA (`rev`) and records the SHA-256 digest of every vendored file (`files`).
- `nix flake check` runs `scripts/upstream.py verify` completely offline inside the Nix sandbox, catching missing, modified, symlinked, or unrecorded files in vendored directories.
- Bumping upstream dependencies is an explicit manual step (`just bump-upstream [source]`) that prints the GitHub `compare` URL and updates `upstream.json` locally so you can audit `git diff` before committing.

## Validation Rules

`scripts/validate.py` checks every skill directory under `skills/`:

- `SKILL.md` exists and starts with valid YAML frontmatter (`---` ... `---`).
- `name` matches the directory name, is 1–64 characters long, and matches `^[a-z0-9]+(-[a-z0-9]+)*$`.
- `description` is non-empty and at most 1024 characters.
- Relative Markdown links in the body resolve inside the skill directory and point to existing files.

## Included Skills

### Authored Skills
- [`atomic-conventional-c4-commits`](skills/atomic-conventional-c4-commits/SKILL.md) — Decompose diffs into minimal, bisectable patches formatted with Conventional Commits v1.0.0 and ZeroMQ C4 discipline.
- [`design-pipeline`](skills/design-pipeline/SKILL.md) — Generate, audit, and refactor UI/UX components with anti-slop constraints, markup pruning rules, heuristic QA (including vendored [`signs-of-ai-design.md`](skills/design-pipeline/references/signs-of-ai-design.md)), and visual asset cleanup pipelines.

### Pinned Upstream Skills
- [`antislop`](skills/antislop/SKILL.md), [`antislop-ui`](skills/antislop-ui/SKILL.md), [`antislop-human`](skills/antislop-human/SKILL.md), [`antislop-layoutmobile`](skills/antislop-layoutmobile/SKILL.md), [`antislop-copywriting`](skills/antislop-copywriting/SKILL.md), [`antislop-code`](skills/antislop-code/SKILL.md) — From `miqdadbadjuber/anti-slop` (MIT).
- [`unslop-ui`](skills/unslop-ui/SKILL.md) — From `felipebasurto/unslop-ui` (MIT).
- [`shadcn`](skills/shadcn/SKILL.md) — From `shadcn-ui/ui` (MIT).
