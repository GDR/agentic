{
  lib,
  stdenv,
  fetchFromGitHub,
  nodejs_24,
  pnpm,
  fetchPnpmDeps,
  pnpmConfigHook,
  makeWrapper,
  beads,
}:
stdenv.mkDerivation (finalAttrs: {
  pname = "bd-board";
  version = "0.2.0";

  src = fetchFromGitHub {
    owner = "jeanpfs";
    repo = "bd-board";
    tag = "v${finalAttrs.version}";
    hash = "sha256-9mdPMZGvKaK4Ge4vV5dx5Pmxs/ngQLJjtPoutrS3Gak=";
  };

  pnpmDeps = fetchPnpmDeps {
    inherit (finalAttrs) pname version src;
    fetcherVersion = 4;
    hash = "sha256-+TfxvT7mBWB9LbOXzc1tirqoXSQ265V9hlQ14zZpvmQ=";
  };

  nativeBuildInputs = [
    nodejs_24
    pnpm
    pnpmConfigHook
    makeWrapper
  ];

  env = {
    TANSTACK_CLI_TELEMETRY_DISABLED = "1";
  };

  buildPhase = ''
    runHook preBuild
    pnpm build
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/lib/bd-board" "$out/bin"
    cp -r .output "$out/lib/bd-board/.output"

    makeWrapper ${lib.getExe nodejs_24} "$out/bin/bd-board" \
      --add-flags "$out/lib/bd-board/.output/server/index.mjs" \
      --prefix PATH : ${lib.makeBinPath [ beads ]} \
      --set-default BD_BIN "bd" \
      --set-default PORT "3009" \
      --set-default TANSTACK_CLI_TELEMETRY_DISABLED "1"
    runHook postInstall
  '';

  meta = {
    description = "Local visual board and multi-project dashboard for the bd beads issue tracker";
    homepage = "https://github.com/jeanpfs/bd-board";
    license = lib.licenses.mit;
    mainProgram = "bd-board";
  };
})
