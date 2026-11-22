---
name: macos-native-design
description: >-
  Enforce Apple Human Interface Guidelines (HIG) and native macOS desktop
  design conventions when building, styling, or auditing AppKit, SwiftUI, or
  macOS desktop interfaces. Routes to vendored HIG skills and prevents
  mobile or generic web patterns from bleeding into macOS apps.
---

# macOS Native Desktop Design

Prevent generic web or mobile patterns (bottom tab bars, floating hamburger drawers, web-style card shadows, missing menu bars) from bleeding into macOS applications.

## Companion Local Skills

Load and apply alongside these locally vendored skills as needed:
- `macos-design-guidelines` — distilled Apple HIG desktop expectations (unified toolbars, split views, menus, shortcuts, dense data)
- `apple-design-hig` — topic-indexed HIG reference (`foundations.md`, `patterns.md`, `components.md`, `inputs.md`, `technologies.md`)
- `design-pipeline` / `antislop*` / `unslop-ui` — anti-slop spacing, contrast, markup pruning, and state coverage when auditing hybrid/web desktop views

## Core macOS Principles

### Window Anatomy
- Use unified toolbars (`Toolbar` / `NSToolbar`) with inline title and search controls positioned cleanly beside traffic-light window controls.
- Never place iOS-style bottom tab bars, floating action buttons, or hamburger navigation drawers in macOS desktop windows.
- Support standard window chrome behaviors: resizable bounds, full-size content view when using vibrancy, and standard window-close vs app-quit lifecycle (`Cmd+W` vs `Cmd+Q`).

### Structural Panes
- Prefer 2-column or 3-column split views (`NavigationSplitView` / `NSSplitView`: Source List sidebar → Content List → Detail / Inspector) over stacked mobile navigation stacks.
- Follow center-equalized spacing and aligned control geometry in toolbars, source lists, and inspector panels.
- Use native sheets, popovers (`NSPopover`), and settings windows (`Settings` scene / `Cmd+,`) instead of full-viewport web modals.

### Keyboard & Menus
- Expose every primary user action in the native system Menu Bar (`CommandMenu` / `NSMenu`) with standard `Cmd` keyboard shortcuts so commands remain discoverable and searchable via Help search.
- Preserve full responder-chain routing, keyboard focus rings, arrow-key list/outline selection, and `Esc` dismissal.

### Visual Materials, Typography & Iconography
- Use native system materials (`Material`, Vibrancy / `NSVisualEffectView`) and dynamic semantic colors (`NSColor` / `Color.primary`, `.secondary`, accent-aware selection highlights) that adapt automatically to Light/Dark appearance and window key state.
- Use SF Pro system text styles (`.title`, `.headline`, `.body`, `.callout`, `.caption`) and tabular numerals for aligned columns/metrics.
- Use SF Symbols with consistent weight and rendering mode rather than heavy blurred web drop shadows or mixed third-party icon packs.

## External Reference Guides
- Layout & native control alignment: [Mario Guzmán Design Guidelines](https://marioaguzman.github.io/design/) & [Apple HIG Archive](https://github.com/gingerbeardman/apple-human-interface-guidelines)
- Native CSS dimensions & tokens (for hybrid/Electron Mac apps): [alex-yelisieiev/apple-design-system](https://github.com/alex-yelisieiev/apple-design-system)
- Native Mac engineering patterns & examples: [hisaac/macOS-Developer-Resources](https://github.com/hisaac/macOS-Developer-Resources) & [serhii-londar/open-source-mac-os-apps](https://github.com/serhii-londar/open-source-mac-os-apps)
