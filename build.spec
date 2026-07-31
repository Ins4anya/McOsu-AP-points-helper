# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for McOsu AP Tracker — onedir + windowed

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web/static', 'web/static'),
        ('Ranks.txt', '.'),
    ],
    hiddenimports=[
        'rosu_pp_py',
        'discord',
        'discord.ext.commands',
        'aiohttp',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'mcsu_bot.db_reader',
        'mcsu_bot_gui.workers.process_worker',
        'mcsu_bot_gui.tabs.control_tab',
        'mcsu_bot_gui.tabs.last_score_tab',
        'mcsu_bot_gui.tabs.ap_breakdown_tab',
        'mcsu_bot.server_client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'pdb',
        'pydoc',
    ],
    noarchive=False,
    module_collection_mode={},
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='McOsuTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# Onedir — builds dist/McOsuTracker/McOsuTracker.exe
