# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller runtime-hook для RAG System Web UI (frozen-режим onedir).

Выполняется до импорта app.py. В onedir-сборке код лежит в <exe_dir>/_internal:
- templates/ и static/ уже внутри _internal — Flask находит их сам;
- mmo.dotx из datas попадает в _internal/docx_templates;
- data/app.db и data/secret_key выносим рядом с exe (долговечные данные,
  не _internal), чтобы сессии и БД переживали перезапуск exe.

Все переменные выставляются через setdefault: явные значения из окружения
имеют приоритет.
"""
import os
import sys

if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    data_dir = os.path.join(exe_dir, "data")
    os.environ.setdefault(
        "MEMO_TEMPLATE_DIR",
        os.path.join(exe_dir, "_internal", "docx_templates"),
    )
    os.environ.setdefault(
        "DATABASE_URL",
        os.path.join("sqlite:///" + data_dir, "app.db"),
    )
    os.environ.setdefault(
        "SECRET_KEY_FILE",
        os.path.join(data_dir, "secret_key"),
    )