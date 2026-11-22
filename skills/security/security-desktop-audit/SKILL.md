---
name: security-desktop-audit
description: Audit desktop-specific OS, IPC, updater, and local privilege boundaries across Electron, Tauri, and native C++/Rust apps.
argument-hint: "[target path or subsystem]"
disable-model-invocation: true
context: fork
allowed-tools: Read, Grep, Glob
---

Audit desktop-specific attack surfaces in: $ARGUMENTS

Inspect actual config, build manifests, IPC handlers, and native bindings before asserting. Check:

1. **Process & IPC Boundary**: Untrusted UI/WebView to privileged core (`preload`/`ipcMain`, `#[tauri::command]` + `capabilities` scopes, D-Bus, Unix domain sockets, named pipes, localhost HTTP servers). Flag missing origin/caller auth, arbitrary path/shell forwarding, or unvalidated deserialization.
2. **Protocol Handlers & Deep Links**: Custom URI schemes (`myapp://`), CLI argument parsing, file-association opens, and OS drag-and-drop paths for argument/command injection or path traversal.
3. **Auto-Updater & Binary Supply Chain**: Signature verification on update payloads, pinned update endpoints over TLS, RPATH/`LD_LIBRARY_PATH`/DLL search-order hijacking, and bundled sidecar integrity.
4. **Local Secrets & Storage**: Tokens/keys stored in plaintext JSON/SQLite/env instead of OS keyring (Keychain, DPAPI, Secret Service), overly broad file permissions (`0644`/`0777`) on config/socket/cache dirs, and sensitive data in crash dumps/logs.
5. **WebView / Sandbox Hardening (if hybrid)**: Explicit `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, strict CSP without `unsafe-eval`, blocked navigation/new-window handlers, and symlink-safe filesystem scopes.

Output ONLY verified findings as `[Severity] file:line — exploit path → minimal fix`. Mark unverifiable runtime checks (code signing, OS entitlements, live updater headers) separately under `Needs Runtime Verification`.
