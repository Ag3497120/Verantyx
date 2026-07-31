# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Verantyx, please **do not** open a
public GitHub Issue.

Instead, use GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/Ag3497120/Verantyx/security) of this repository.
2. Click **"Report a vulnerability"**.
3. Describe the issue, including steps to reproduce and potential impact.

You should receive an acknowledgement within a reasonable timeframe. Please
give us a chance to investigate and release a fix before any public
disclosure.

## Scope

This covers the Verantyx macOS app (`cli/VerantyxIDE`), the bundled
`vera-memory` binary, and the `jcross_engine_glm` Rust engine embedded as a
`.dylib`. Vulnerabilities involving prompt injection against local LLM
backends, or issues in third-party dependencies, are still welcome reports —
we'll help route them appropriately.

## Supported Versions

This project does not yet maintain multiple release branches. Only the latest
version on `main` receives security fixes.
