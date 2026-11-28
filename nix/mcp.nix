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

    beads =
      {
        pkgs ? null,
        package ? null,
        beadsPackage ? null,
        env ? { },
      }:
      let
        resolvedBeads =
          if beadsPackage != null then
            beadsPackage
          else if pkgs != null then
            pkgs.beads
          else
            null;
        resolvedPackage =
          if package != null then
            package
          else if pkgs != null then
            pkgs.callPackage ./beads-mcp.nix { beads = resolvedBeads; }
          else
            null;
      in
      {
        command = if resolvedPackage != null then lib.getExe resolvedPackage else "beads-mcp";
        args = [ ];
        packages =
          lib.optional (resolvedPackage != null) resolvedPackage
          ++ lib.optional (resolvedBeads != null) resolvedBeads;
      }
      // lib.optionalAttrs (env != { }) { inherit env; };

    ghidra =
      {
        pkgs ? null,
        url ? "http://127.0.0.1:8089",
        package ? null,
        withGhidra ? (pkgs != null),
        ghidra ? null,
        extraExtensions ? (_: [ ]),
      }:
      let
        resolvedPackage =
          if package != null then
            package
          else if pkgs != null then
            pkgs.callPackage ./ghidra-mcp-bridge.nix { }
          else
            null;
        baseGhidra = if ghidra != null then ghidra else pkgs.ghidra;
        ghidraPkg =
          if withGhidra then
            assert pkgs != null;
            let
              extension = pkgs.callPackage ./ghidra-mcp-extension.nix { };
            in
            baseGhidra.withExtensions (p: [ extension ] ++ extraExtensions p)
          else
            null;
      in
      {
        command = if resolvedPackage != null then lib.getExe resolvedPackage else "bridge-mcp-ghidra";
        args = [ ];
        env = {
          GHIDRA_MCP_URL = url;
        };
        packages =
          lib.optional (resolvedPackage != null) resolvedPackage
          ++ lib.optional (ghidraPkg != null) ghidraPkg;
      };

    tracy =
      {
        url ? "http://127.0.0.1:47380/mcp",
      }:
      {
        inherit url;
      };

    rea =
      {
        pkgs,
        package ? pkgs.callPackage ./rea.nix { },
        withGhidra ? true,
        ghidra ? pkgs.ghidra,
        jdk ? pkgs.jdk25,
        env ? { },
      }:
      let
        defaultEnv = lib.optionalAttrs withGhidra {
          GHIDRA_INSTALL_DIR = "${ghidra}/lib/ghidra";
          JAVA_HOME = "${jdk.home}";
        };
        mergedEnv = defaultEnv // env;
      in
      {
        command = lib.getExe package;
        args = [ "mcp" ];
        packages = [ package ] ++ lib.optional withGhidra jdk;
      }
      // lib.optionalAttrs (mergedEnv != { }) { env = mergedEnv; };
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
