"""PyInstaller runtime-hook для RAG System (frozen, onedir).

Эквивалент запуска с -X utf8: в обычном режиме PyInstaller не унаследует
флаг, а консоль Windows по умолчанию cp1251 — кириллица/эмодзи в print
ломаются. Переключаем stdout/stderr на utf-8 до старта app.py.
"""
import sys

if getattr(sys, "frozen", False):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass