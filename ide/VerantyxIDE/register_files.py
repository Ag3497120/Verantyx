#!/usr/bin/env python3
"""
register_files.py — 安全に Swift ファイルを Xcode プロジェクトに登録する。
plutil で検証しながら実行。失敗時は自動 git restore する。
"""
import hashlib, re, subprocess, sys, os

PBX = '/Users/motonishikoudai/verantyx-cli/VerantyxIDE/Verantyx.xcodeproj/project.pbxproj'
PROJ_ROOT = '/Users/motonishikoudai/verantyx-cli/VerantyxIDE'

def uuq(seed):
    return hashlib.md5(seed.encode()).hexdigest().upper()[:24]

def validate(path):
    r = subprocess.run(['plutil', '-lint', path], capture_output=True)
    return r.returncode == 0, r.stderr.decode().strip()

def restore():
    subprocess.run(['git', 'checkout', 'HEAD', '--',
                    'Verantyx.xcodeproj/project.pbxproj'], cwd=PROJ_ROOT)
    print("🔄 Restored from git HEAD")

with open(PBX) as f:
    content = f.read()

ok, err = validate(PBX)
if not ok:
    print(f"ERROR: PBX already invalid: {err}")
    sys.exit(1)
print("✓ PBX valid before edits\n")

# ── Files to register ───────────────────────────────────────────────────────
# (filename, is_views_group)
FILES = [
    ("HumanPriorityModeView.swift", True),
    ("ProjectSearchEngine.swift",   False),
    ("GitEngine.swift",             False),
    ("LSPClient.swift",             False),
    ("GlobalSearchView.swift",      True),
    ("GitPanelView.swift",          True),
]

# ── Find stable anchors ─────────────────────────────────────────────────────
# Use VerantyxApp.swift / DiffEngine.swift as anchors (always in HEAD)
def find_anchor(pattern):
    m = re.search(pattern, content)
    return m.group(0) if m else None

engine_group_anchor = find_anchor(r'[A-F0-9]{24} /\* DiffEngine\.swift \*/')
views_group_anchor  = find_anchor(r'[A-F0-9]{24} /\* ActivityBarView\.swift \*/')
sources_bf_anchor   = find_anchor(r'[A-F0-9]{24} /\* DiffEngine\.swift in Sources \*/')
file_ref_end   = '\t\t/* End PBXFileReference section */'
build_file_end = '\t\t/* End PBXBuildFile section */'

assert engine_group_anchor, "DiffEngine group anchor not found"
assert views_group_anchor,  "ActivityBarView group anchor not found"
assert sources_bf_anchor,   "DiffEngine Sources anchor not found"

print(f"Engine anchor: {engine_group_anchor}")
print(f"Views anchor:  {views_group_anchor}")
print(f"Sources anchor:{sources_bf_anchor}\n")

# ── Register each file ──────────────────────────────────────────────────────
for fname, is_view in FILES:
    if fname in content:
        print(f"  ✓ SKIP (exists): {fname}")
        continue

    fr_uuid = uuq(f"clean_fr_{fname}")
    bf_uuid = uuq(f"clean_bf_{fname}")

    # 1. PBXFileReference entry
    fr_line = (
        f'\t\t{fr_uuid} /* {fname} */ = '
        f'{{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; '
        f'path = {fname}; sourceTree = "<group>"; }};\n'
    )
    content = content.replace(file_ref_end, fr_line + file_ref_end)

    # 2. PBXBuildFile entry
    bf_line = (
        f'\t\t{bf_uuid} /* {fname} in Sources */ = '
        f'{{isa = PBXBuildFile; fileRef = {fr_uuid} /* {fname} */; }};\n'
    )
    content = content.replace(build_file_end, bf_line + build_file_end)

    # 3. Add to group children
    anchor = views_group_anchor if is_view else engine_group_anchor
    repl = anchor + f',\n\t\t\t\t{fr_uuid} /* {fname} */,'
    content = content.replace(anchor + ',', repl, 1)

    # 4. Add to Sources build phase
    sources_repl = sources_bf_anchor + f',\n\t\t\t\t{bf_uuid} /* {fname} in Sources */,'
    content = content.replace(sources_bf_anchor + ',', sources_repl, 1)

    print(f"  ✓ Registered: {fname}  fr={fr_uuid}  bf={bf_uuid}")

# ── Write & validate ─────────────────────────────────────────────────────────
with open(PBX, 'w') as f:
    f.write(content)

ok, err = validate(PBX)
if ok:
    print("\n✅ project.pbxproj VALID — all files registered")
else:
    print(f"\n❌ INVALID: {err}")
    restore()
    sys.exit(1)
