import os


def _unidic_dicdir():
    import unidic_lite
    return os.path.join(os.path.dirname(unidic_lite.__file__), 'dicdir')


# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['vera_entry.py'],
    pathex=[],
    binaries=[],
    # The failure-domain packs are DATA now, not code. Without this the
    # frozen binary would load two built-in packs and silently lose the
    # twelve JSON ones — a failure that looks like 'the field packs were
    # never written' rather than 'they were not shipped'.
    datas=[('verantyx/failure_packs', 'verantyx/failure_packs'),
           # The Japanese grammar is data, not code — a frozen binary
           # without it would run with no Japanese at all, silently.
           ('verantyx/lang_data', 'verantyx/lang_data'),
           # UniDic, 248 MB, and the binary goes 28 MB -> ~277 MB for it.
           # Worth it: without the dictionary every door that reads
           # Japanese morphology refuses with VOID_ENVIRONMENT, which is
           # honest and also means domain registration, case frames and
           # polarity simply never work in a shipped build. Measured on
           # the previous freeze: `vera_domain_text` returned
           # {'verdict': 'VOID_ENVIRONMENT', 'missing': ['unidic_lite']}.
           (_unidic_dicdir(), 'unidic_lite/dicdir')],
    hiddenimports=['mcp', 'mcp.server.fastmcp',
                   'fugashi', 'unidic_lite',
                   # Without a PDF reader, every document door refuses the
                   # most common document there is. Measured 2026-08-16: a
                   # contest PDF returned UNKNOWN_UNREADABLE from
                   # vera_domain and UNKNOWN_NO_PARSER from load_documents,
                   # so the shipped engine could not read one byte of it.
                   'pypdf', 'pypdf._reader'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='vera-memory',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
