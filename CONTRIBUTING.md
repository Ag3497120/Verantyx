# Contributing to Verantyx

Thanks for your interest in Verantyx. This document covers how to report bugs,
propose changes, and submit pull requests.

## Before you start

- Check [existing Issues](https://github.com/Ag3497120/Verantyx/issues) to
  avoid duplicates.
- For open-ended design questions or "what if" ideas, use
  [Discussions](https://github.com/Ag3497120/Verantyx/discussions) instead of
  Issues — Issues are for concrete, actionable items.
- See the [Wiki](https://github.com/Ag3497120/Verantyx/wiki) for architecture
  background before making structural changes (e.g. the GapNode/quarantine
  design, the Vera-harness HTTP+SSE path) — several design decisions are
  deliberate and documented there.

## Reporting bugs

Open an [Issue](https://github.com/Ag3497120/Verantyx/issues/new) with:

- What you did, what you expected, what actually happened
- macOS version and Apple Silicon/Intel
- Relevant log output if available (the app writes harness logs to
  `~/Library/Application Support/Verantyx/jgen/serve.log`)

## Proposing changes

1. Fork the repo and create a branch from `main`.
2. Make your change. For Swift changes in `cli/VerantyxIDE`, register any new
   file in `Verantyx.xcodeproj/project.pbxproj` (PBXBuildFile, PBXFileReference,
   group children, Sources build phase — all four are required or the file
   won't compile into the target).
3. Build and verify locally:
   ```bash
   cd cli/VerantyxIDE
   xcodebuild -project Verantyx.xcodeproj -scheme Verantyx -configuration Debug build
   ```
   (A pre-existing `verantyx-browser` codesign warning during local builds is
   expected and unrelated to your change.)
4. Open a pull request describing what changed and why. Reference any related
   Issue.

## Security issues

Do not open a public Issue for security vulnerabilities. See
[SECURITY.md](./SECURITY.md).

## Code of Conduct

This project follows the [Code of Conduct](./CODE_OF_CONDUCT.md).
