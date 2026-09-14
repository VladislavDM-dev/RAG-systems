# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller runtime-hook для RAG System Web UI (frozen-режим onedir).

Выполняется до импорта app.py. В onedir-сборке код лежит в <exe_dir>/_internal:
- templates/ и static/ уже внутри _internal — Flask находит их сам;
- mmo.dotx из datas попадает в _internal/docx_templates;
- users.json и data/ выносим рядом с exe (долговечные данные, не _internal);
- каталог служебок: MEMO_CORPUS_DIR (по умолчанию <exe_dir>/../out).

Все переменные выставляются через setdefault: явные значения из окружения
имеют приоритет.
"""
import os
import sys

if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    os.environ.setdefault(
        "MEMO_TEMPLATE_DIR",
        os.path.join(exe_dir, "_internal", "docx_templates"),
    )
    os.environ.setdefault("USERS_FILE", os.path.join(exe_dir, "users.json"))
    os.environ.setdefault("DATA_DIR", os.path.join(exe_dir, "data"))
    os.environ.setdefault("MEMO_CORPUS_DIR", os.path.join(exe_dir, "..", "out"))