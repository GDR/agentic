{
  config,
  lib,
  pkgs,
  ...
}:
let
  layout = import ./layout.nix { inherit lib; };
  cfg = config.programs.agentic;

  resolveRepoPath =
    raw:
    if raw == "~" then
      config.home.homeDirectory
    else if lib.hasPrefix "/" raw then
      raw
    else if lib.hasPrefix "~/" raw then
      "${config.home.homeDirectory}/${lib.removePrefix "~/" raw}"
    else
      "${config.home.homeDirectory}/${lib.removePrefix "./" raw}";

  resolvedRepoPath = resolveRepoPath cfg.repoPath;

  mkCommitSkillGate =
    harness:
    pkgs.writeShellScript "agentic-commit-skill-gate-${harness}" ''
      script="${resolvedRepoPath}/hooks/commit_skill_gate.py"
      if [ -f "$script" ]; then
        exec "${lib.getExe pkgs.python3}" -B "$script" --harness "${harness}"
      fi
      ${lib.optionalString (harness == "antigravity") ''printf '{"decision":"allow"}\n' ''}
    '';

  antigravityCommitGate = mkCommitSkillGate "antigravity";
  claudeCommitGate = mkCommitSkillGate "claude";

  # Idempotently inject/update our PreToolUse Bash matcher in ~/.claude/settings.json
  # without clobbering user settings or interactive Claude Code state.
  mergeClaudeHooksScript = ../hooks/merge_claude_hooks.py;
in
{
  options.programs.agentic = {
    enable = lib.mkEnableOption "agentic harness wiring (skills manifest and PreToolUse commit skill gate)";

    repoPath = lib.mkOption {
      type = lib.types.str;
      default = "Workspaces/gdr/agentic";
      description = "Checkout path of the agentic repository (relative to home.homeDirectory, ~/, or absolute).";
    };

    skillCategories = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = layout.skillCategories;
      description = "Skill category directories under skills/ emitted to ~/.gemini/config/skills.json.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.file.".gemini/config/skills.json".text = builtins.toJSON {
      entries = map (cat: {
        path = "${resolvedRepoPath}/skills/${cat}";
      }) cfg.skillCategories;
    };

    home.file.".gemini/config/hooks.json".text = builtins.toJSON {
      commit-skill-gate = {
        PreToolUse = [
          {
            matcher = "run_command";
            hooks = [
              {
                type = "command";
                command = "${antigravityCommitGate}";
                timeout = 10;
              }
            ];
          }
        ];
      };
    };

    home.activation.agenticClaudeHooks = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run ${lib.escapeShellArg (lib.getExe pkgs.python3)} -B ${lib.escapeShellArg "${mergeClaudeHooksScript}"} ${lib.escapeShellArg "${config.home.homeDirectory}/.claude/settings.json"} ${lib.escapeShellArg "${claudeCommitGate}"} || warnEcho "agenticClaudeHooks merge failed; continuing"
    '';
  };
}
