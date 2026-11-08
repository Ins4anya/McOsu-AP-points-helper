# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for McOsu AP Tracker — onedir + windowed (NiceGUI desktop)

from PyInstaller.utils.hooks import collect_all

nicegui_datas, nicegui_binaries, nicegui_hiddenimports = collect_all('nicegui')
pywebview_datas, pywebview_binaries, pywebview_hiddenimports = collect_all('webview')

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=nicegui_binaries + pywebview_binaries,
    datas=[
        ('web/static', 'web/static'),
        ('server/templates', 'server/templates'),
        ('server/static', 'server/static'),
        ('server/alembic.ini', 'server'),
        ('server/alembic', 'server/alembic'),
        ('Ranks.txt', '.'),
        ('assets/favicon.ico', 'assets'),
    ] + nicegui_datas + pywebview_datas,
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
        'mcsu_bot.server_client',
        'server.main',
        'server.config',
        'server.database',
        'server.auth',
        'server.challenge',
        'server.streak',
        'server.beatmap_picker',
        'server.ranked',
        'server.ranked_rules',
        'server.skills',
        'server.backfill_links',
        'server.routers',
        'server.routers.api',
        'server.routers.auth',
        'server.routers.pages',
        'aiosqlite',
        'alembic',
        'jinja2',
        'mcsu_gui.app',
        'mcsu_gui.tabs.control',
        'mcsu_gui.tabs.last_score',
        'mcsu_gui.tabs.ap_breakdown',
        'mcsu_gui.tabs.ranked',
        # legacy fallback (kept)
        'mcsu_bot_gui.workers.process_worker',
        'mcsu_bot_gui.tabs.control_tab',
        'mcsu_bot_gui.tabs.last_score_tab',
        'mcsu_bot_gui.tabs.ap_breakdown_tab',
    ] + nicegui_hiddenimports + pywebview_hiddenimports,
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
    icon='assets/favicon.ico',
)

# Onedir — builds dist/McOsuTracker/McOsuTracker.exe