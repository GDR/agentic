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
│   └── validate.py         # Skill structure, frontmatter, and relative-link validator
├── flake.nix               # Nix flake (devShell, formatter, skills package, validate-skills check)
└── justfile                # Task runner recipes (new, validate, check, fmt)
```

## Authoring & Validation

Enter the development shell (or prefix commands with `nix develop -c`):

```bash
nix develop
```

Common workflows:

```bash
just new <name>     # Scaffold skills/<name>/SKILL.md from template
just validate       # Run scripts/validate.py against skills/
just check          # Run validator and nix flake check
just fmt            # Format Nix files via nix fmt (nixfmt-tree)
```

You can also run Nix commands directly:

```bash
nix flake check               # Run checks.<system>.validate-skills
nix build .#skills            # Build packages.<system>.skills output
nix fmt                       # Format Nix files
```

> **Note:** `nix flake check` evaluates Git-tracked files only. After scaffolding a new skill with `just new <name>`, stage it with `git add skills/<name>` before running `nix flake check` or `just check`.

## Validation Rules

`scripts/validate.py` checks every skill directory under `skills/`:

- `SKILL.md` exists and starts with valid YAML frontmatter (`---` ... `---`).
- `name` matches the directory name, is 1–64 characters long, and matches `^[a-z0-9]+(-[a-z0-9]+)*$`.
- `description` is non-empty and at most 1024 characters.
- Relative Markdown links in the body resolve inside the skill directory and point to existing files.
