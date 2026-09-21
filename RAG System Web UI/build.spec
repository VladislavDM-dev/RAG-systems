# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: RAG System Web UI (Flask-интерфейс, порт 80).

onedir-EXE 'RAG System Web UI'. Бандлятся шаблоны Flask, статика и шаблон
служебной записки mmo.dotx (уходят в <exe_dir>/_internal). data/app.db и
data/secret_key создаются при первом запуске рядом с exe (см. hook_runtime.py).
Корпус служебок Web UI не читает: всё работает через RAG API.

Запуск (из каталога RAG System Web UI):
    venv python -m PyInstaller --noconfirm --clean build.spec
"""
import os

SPECDIR_ABS = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(SPECDIR_ABS, "templates"), "templates"),
    (os.path.join(SPECDIR_ABS, "static"), "static"),
    # Шаблон лежит в корне репозитория (../docx_templates/mmо.dotx).
    (os.path.join(SPECDIR_ABS, "..", "docx_templates", "mmo.dotx"), "docx_templates"),
]

a = Analysis(
    [os.path.join(SPECDIR_ABS, "app.py")],
    pathex=[SPECDIR_ABS],
    binaries=[],
    datas=datas,
    hiddenimports=["docx"],  # python-docx (нет в requirements.txt Web UI)
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPECDIR_ABS, "hook_runtime.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RAG System Web UI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # логи Flask в консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RAG System Web UI",
)