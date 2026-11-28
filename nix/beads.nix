{ lib }:
let
  syncScript = ../beads/sync.py;
  defaultRuleFile = ../beads/rule.md;
  defaultSkillsDir = ../skills/beads;

  mkBeads =
    {
      pkgs,
      package ? pkgs.beads,
      boardPackage ? pkgs.callPackage ./bd-board.nix { beads = package; },
      ruleFile ? defaultRuleFile,
      skillsDir ? defaultSkillsDir,
      syncRule ? true,
      syncSkills ? true,
      excludeGit ? true,
      autoInit ? false,
    }:
    let
      python = lib.getExe pkgs.python3;
      syncFlags =
        lib.optional (!syncRule) "--no-rule"
        ++ lib.optional (!syncSkills) "--no-skills"
        ++ lib.optional (!excludeGit) "--no-exclude"
        ++ lib.optional autoInit "--auto-init";
      shellHook = ''
        if [ "''${AGENTIC_BEADS_DISABLE:-0}" != "1" ]; then
          ${lib.escapeShellArg python} -B ${lib.escapeShellArg "${syncScript}"} \
            --root "$PWD" \
            --rule ${lib.escapeShellArg "${ruleFile}"} \
            --skills-dir ${lib.escapeShellArg "${skillsDir}"} \
            ${lib.escapeShellArgs syncFlags}
        fi
      '';
    in
    {
      packages = [
        package
      ]
      ++ lib.optional (boardPackage != null) boardPackage;
      inherit
        shellHook
        boardPackage
        ruleFile
        skillsDir
        ;
    };
in
{
  inherit mkBeads;
}
