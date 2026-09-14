# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: RAG System (ядро, Flask API на :11455).

Собирает onedir-EXE 'RAG System' со всеми зависимостями (llama_index, faiss,
win32com). Data-файлы не бандлятся: settings.json и .cache создаются при
первом запуске рядом с модулем.

Запуск (из каталога RAG System):
    venv python -m PyInstaller --noconfirm --clean build.spec

Runtime требует ОС-уровня: Word COM для .doc/.docx, ABBYY FineReader 15
для .pdf (см. AGENTS.md).
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

SPECDIR_ABS = os.path.abspath(SPECPATH)

# tiktoken находит кодировки через pkgutil.iter_modules по tiktoken_ext
# (namespace-пакет): модуль должен лежать на диске в _internal, иначе
# "ValueError: Unknown encoding cl100k_base. Plugins found: []".
datas = collect_data_files("tiktoken_ext", include_py_files=True)
hiddenimports = collect_submodules("rag_engine")

# Провайдеры импортируются внутри методов providers.py/rag_engine.py —
# явно закрепляем, чтобы сборка не пропустила их.
hiddenimports += [
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "ollama",
    "openai",
    "PyPDF2",
    "pythoncom",
    "win32com",
    "win32com.client",
    "win32com.client.gencache",
    "docx",
    # llama-index интеграции, подключаемые точечно
    "llama_index.llms.ollama",
    "llama_index.embeddings.ollama",
    "llama_index.llms.openai_like",
    "llama_index.embeddings.openai",
    "llama_index.vector_stores.faiss",
]

# Нативные .dll/.so у faiss и numpy (libfaiss, numpy.libs) в wheels.
binaries = []
for _pkg in ("faiss", "numpy"):
    binaries += collect_dynamic_libs(_pkg)

a = Analysis(
    [os.path.join(SPECDIR_ABS, "app.py")],
    pathex=[SPECDIR_ABS],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="RAG System",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # в консоли видны логи Flask/статус синхронизации
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
    name="RAG System",
)