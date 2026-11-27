{
  lib,
  stdenvNoCC,
  fetchurl,
  unzip,
}:
stdenvNoCC.mkDerivation rec {
  pname = "ghidra-mcp-extension";
  version = "7.1.0";

  src = fetchurl {
    url = "https://github.com/bethington/ghidra-mcp/releases/download/v${version}/GhidraMCP-${version}.zip";
    hash = "sha256-AVF2wYQt7GNcpEkH9ar9G+ijt/MHz0AaE61kM2pMGLQ=";
  };

  nativeBuildInputs = [ unzip ];

  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    dest="$out/lib/ghidra/Ghidra/Extensions"
    mkdir -p "$dest"
    unzip -q "$src" -d "$dest"

    runHook postInstall
  '';

  meta = {
    description = "GhidraMCP Java extension for Ghidra 12.2 (bethington/ghidra-mcp)";
    homepage = "https://github.com/bethington/ghidra-mcp";
    license = lib.licenses.asl20;
    platforms = lib.platforms.all;
  };
}
