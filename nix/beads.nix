{ lib }:
let
  uiScript = ../beads/ui.py;
  syncScript = ../beads/sync.py;
  defaultRuleFile = ../beads/rule.md;

  mkBeadsUi =
    {
      pkgs,
      beadsPackage ? pkgs.beads,
      defaultPort ? 7474,
    }:
    pkgs.writeShellScriptBin "beads-ui" ''
      export PATH="${lib.makeBinPath [ beadsPackage ]}:$PATH"
      export BEADS_UI_PORT="''${BEADS_UI_PORT:-${toString defaultPort}}"
      exec ${lib.escapeShellArg (lib.getExe pkgs.python3)} -B ${lib.escapeShellArg "${uiScript}"} "$@"
    '';

  mkBeads =
    {
      pkgs,
      package ? pkgs.beads,
      uiPackage ? mkBeadsUi {
        inherit pkgs defaultPort;
        beadsPackage = package;
      },
      ruleFile ? defaultRuleFile,
      syncRule ? true,
      excludeGit ? true,
      autoInit ? false,
      defaultPort ? 7474,
    }:
    let
      python = lib.getExe pkgs.python3;
      syncFlags =
        lib.optional (!syncRule) "--no-rule"
        ++ lib.optional (!excludeGit) "--no-exclude"
        ++ lib.optional autoInit "--auto-init";
      shellHook = ''
        if [ "''${AGENTIC_BEADS_DISABLE:-0}" != "1" ]; then
          ${lib.escapeShellArg python} -B ${lib.escapeShellArg "${syncScript}"} \
            --root "$PWD" \
            --rule ${lib.escapeShellArg "${ruleFile}"} \
            ${lib.escapeShellArgs syncFlags}
        fi
      '';
    in
    {
      packages = [
        package
        uiPackage
      ];
      inherit shellHook uiPackage ruleFile;
    };
in
{
  inherit mkBeads mkBeadsUi;
}
