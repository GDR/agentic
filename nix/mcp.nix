{ lib }:
let
  defaultHarnesses = [
    "antigravity"
    "claude"
  ];
  allHarnesses = [
    "antigravity"
    "claude"
    "codex"
    "opencode"
    "gemini"
  ];

  mcp = {
    inherit defaultHarnesses allHarnesses;

    nixos =
      {
        pkgs,
        package ? pkgs.mcp-nixos,
      }:
      {
        command = lib.getExe package;
        args = [ ];
        packages = [ package ];
      };

    ghidra =
      {
        url ? "http://127.0.0.1:8089",
        package ? null,
      }:
      {
        command = if package != null then lib.getExe package else "bridge-mcp-ghidra";
        args = [ ];
        env = {
          GHIDRA_MCP_URL = url;
        };
        packages = lib.optional (package != null) package;
      };
  };

  syncScript = ../mcp/sync.py;

  mkMcp =
    {
      pkgs,
      servers ? { },
      harnesses ? defaultHarnesses,
      projectEnvFile ? ".agents/mcp.env",
      excludeGit ? true,
    }:
    let
      packages = lib.concatLists (lib.mapAttrsToList (_: s: s.packages or [ ]) servers);
      cleanServers = lib.mapAttrs (_: s: builtins.removeAttrs s [ "packages" ]) servers;
      specData = {
        inherit harnesses projectEnvFile excludeGit;
        servers = cleanServers;
      };
      specFile = pkgs.writeText "agentic-mcp-spec.json" (builtins.toJSON specData);
      python = lib.getExe pkgs.python3;
      shellHook = ''
        if [ "''${AGENTIC_MCP_DISABLE:-0}" != "1" ]; then
          ${lib.escapeShellArg "${python}"} -B ${lib.escapeShellArg "${syncScript}"} \
            --spec ${lib.escapeShellArg "${specFile}"} \
            --root "$PWD"
        fi
      '';
    in
    {
      inherit packages shellHook;
      spec = specFile;
    };
in
{
  inherit mcp mkMcp;
}
