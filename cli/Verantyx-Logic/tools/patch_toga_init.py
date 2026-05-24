from pathlib import Path

# Fix travertino
travertino_init = Path("verantyx_ios/src/travertino/__init__.py")
if travertino_init.exists():
    content = travertino_init.read_text()
    # Replace dynamic versioning with static
    # Using regex-like replacement for robustness might be better, but simple replace works if file is standard
    if "from . import _package_version" in content:
        content = content.replace("from . import _package_version", "# from . import _package_version")
        content = content.replace("__version__ = _package_version(__file__, __name__)", '__version__ = "0.3.0"')
        travertino_init.write_text(content)
        print("Patched travertino/__init__.py")
    else:
        print("travertino/__init__.py content mismatch, skipping patch.")

# Fix toga
toga_init = Path("verantyx_ios/src/toga/__init__.py")
if toga_init.exists():
    content = toga_init.read_text()
    if "from travertino import _package_version" in content:
        content = content.replace("from travertino import _package_version", "# from travertino import _package_version")
        content = content.replace("__version__ = _package_version(__file__, __name__)", '__version__ = "0.4.0"')
        toga_init.write_text(content)
        print("Patched toga/__init__.py")
    else:
        print("toga/__init__.py content mismatch, skipping patch.")
