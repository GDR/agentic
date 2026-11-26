{
  lib,
  stdenv,
  fetchurl,
  makeWrapper,
  autoPatchelfHook,
  nodejs_24,
}:
let
  pname = "rea-agents";
  version = "6.10.1";
  nodePtyTarget =
    {
      "x86_64-linux" = "linux-x64";
      "aarch64-linux" = "linux-arm64";
      "x86_64-darwin" = "darwin-x64";
      "aarch64-darwin" = "darwin-arm64";
    }
    .${stdenv.hostPlatform.system}
      or (throw "rea-agents: unsupported system ${stdenv.hostPlatform.system}");
in
stdenv.mkDerivation {
  inherit pname version;

  src = fetchurl {
    url = "https://registry.npmjs.org/rea-agents/-/rea-agents-${version}.tgz";
    hash = "sha512-3AWrfFEXppvC98FWhZR2Tzulnqs5xJQrSKmAub6+QME/I58Pr3h8pHqqwM30z2DvlnIx/8Hsu8woMngfi4SNyg==";
  };

  nativeBuildInputs = [
    makeWrapper
  ]
  ++ lib.optionals stdenv.hostPlatform.isLinux [
    autoPatchelfHook
  ];

  buildInputs = lib.optionals stdenv.hostPlatform.isLinux [
    stdenv.cc.cc.lib
  ];

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    dest="$out/lib/node_modules/rea-agents"
    mkdir -p "$dest" "$out/bin"
    cp -a . "$dest/"

    # Drop foreign-platform native prebuilds so autoPatchelfHook only inspects
    # binaries matching the host architecture.
    rm -rf "$dest/native/windows"
    for dir in "$dest"/node_modules/@lydell/node-pty-*; do
      if [ "$(basename "$dir")" != "node-pty-${nodePtyTarget}" ]; then
        rm -rf "$dir"
      fi
    done

    for bin in rea rea-agents; do
      makeWrapper "${lib.getExe nodejs_24}" "$out/bin/$bin" \
        --add-flags "$dest/scripts/rea.mjs"
    done

    runHook postInstall
  '';

  meta = {
    description = "Reverse engineer anything from your terminal or agent with one CLI and MCP server";
    homepage = "https://github.com/morluto/rea";
    license = lib.licenses.mit;
    mainProgram = "rea";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
      "x86_64-darwin"
      "aarch64-darwin"
    ];
  };
}
