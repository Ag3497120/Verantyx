## What does this PR do?

<!-- Concise summary of the change and why it's needed -->

## Related Issue(s)

<!-- e.g. Closes #12 -->

## How was this tested?

- [ ] Built and ran locally (`xcodebuild ... build` for Swift changes, or the
      relevant offline test for Python/Rust changes)
- [ ] Manually verified the affected feature end-to-end
- [ ] N/A (docs-only change)

## Checklist

- [ ] New Swift files are registered in `project.pbxproj` (all 4 anchors: PBXBuildFile, PBXFileReference, group children, Sources build phase)
- [ ] No secrets, absolute local paths, or machine-specific values were introduced
- [ ] Changes follow the existing quarantine/approval pattern for anything that writes to Vera's trusted store (see the [Architecture wiki page](https://github.com/Ag3497120/Verantyx/wiki/Architecture) if unsure)
