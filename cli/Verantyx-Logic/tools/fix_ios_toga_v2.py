import shutil
import os
from pathlib import Path

# Path to system site-packages
SITE_PACKAGES = "/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages"
# Move to SRC root so 'import toga' works directly
DEST = Path("verantyx_ios/src")

print(f"Fixing Toga installation in {DEST}...")

# 1. Clean existing copies
for folder in ["toga", "toga_iOS", "rubicon", "fontTools", "travertino"]:
    path = DEST / folder
    if path.exists():
        if path.is_dir(): shutil.rmtree(path)
        else: os.remove(path)

# 2. Copy toga-core
toga_core_src = os.path.join(SITE_PACKAGES, "toga")
if os.path.exists(toga_core_src):
    shutil.copytree(toga_core_src, DEST / "toga")
    print("Copied toga-core.")

# 3. Merge toga-iOS content
toga_ios_inner = Path(SITE_PACKAGES) / "toga_iOS" / "toga"
if toga_ios_inner.exists():
    for item in toga_ios_inner.iterdir():
        dest_item = DEST / "toga" / item.name
        if item.is_dir():
            if dest_item.exists(): shutil.rmtree(dest_item)
            shutil.copytree(item, dest_item)
        else:
            shutil.copy2(item, dest_item)
    print("Merged toga-iOS into toga namespace.")

# 4. Copy all other dependencies
deps = ["rubicon", "fontTools", "travertino", "toga_iOS"]
for dep in deps:
    src_path = os.path.join(SITE_PACKAGES, dep)
    if os.path.exists(src_path):
        shutil.copytree(src_path, DEST / dep)
        print(f"Copied {dep}.")

print("Toga Namespace Merged Successfully in SRC root!")
