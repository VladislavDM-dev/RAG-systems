import os
import re
import threading
from typing import List, Dict, Any

import pythoncom
import win32com.client
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


# Общий (для .doc и .docx) реентерабельный лок: Word допускает только
# один COM-инстанс за раз, параллельные Dispatch("Word.Application")
# из нескольких потоков заставляют Word зависать.
_WORD_LOCK = threading.RLock()

# Инициализация COM-апартмента должна выполняться один раз на поток.
_tls = threading.local()


def _ensure_com():
    """Инициализирует COM-апартмент текущего потока (идемпотентно)."""
    if not getattr(_tls, "com_initialized", False):
        pythoncom.CoInitialize()
        _tls.com_initialized = True


def _teardown_com():
    """Освобождает COM-апартмент текущего потока (балансирует CoInitialize)."""
    if getattr(_tls, "com_initialized", False):
        try:
            pythoncom.CoUninitialize()
        finally:
            _tls.com_initialized = False


class DocxParser:
    def __init__(self, file_path: str, image_output_dir: str = None):
        """
        Инициализация парсера.
        :param file_path: Путь к .docx файлу.
        :param image_output_dir: Не используется (удалено для оптимизации).
        """
        self.file_path = file_path
        self.doc = Document(file_path)

    @staticmethod
    def get_page_count(docx_path: str) -> int:
        """Количество страниц через Word COM. Потокобезопасно (сериализовано)."""
        with _WORD_LOCK:
            page_count = 0
            word_app = None
            doc = None
            _ensure_com()
            try:
                word_app = win32com.client.Dispatch("Word.Application")
                word_app.Visible = False
                word_app.ScreenUpdating = False
                word_app.DisplayAlerts = 0  # wdAlertsNone — без модальных диалогов

                doc = word_app.Documents.Open(
                    os.path.abspath(docx_path),
                    ReadOnly=True,
                    AddToRecentFiles=False,
                    ConfirmConversions=False,
                )
                page_count = doc.Content.Information(4)
            except Exception as exc:
                raise RuntimeError(f"Ошибка получения числа страниц .docx: {exc}")
            finally:
                try:
                    if doc is not None:
                        doc.Close(False)
                except Exception:
                    pass
                try:
                    if word_app is not None:
                        word_app.Quit()
                except Exception:
                    pass
                _teardown_com()
            return page_count

    def parse(self,check_page_count = True, page_count = 0):
        if check_page_count:
            page_count = self.get_page_count(self.file_path)
            if page_count == 0 or page_count > 10:
                return page_count, None

        """
        Парсит документ и возвращает строку в формате Markdown.
        Сохраняет структуру: заголовки, списки, таблицы. Изображения игнорируются.
        """
        markdown_content = []

        for element in self.doc.element.body:
            # Обработка параграфов
            if element.tag.endswith('p'):
                para = Paragraph(element, self.doc)
                md_text = self._parse_paragraph(para)
                if md_text.strip():
                    markdown_content.append(md_text)

            # Обработка таблиц
            elif element.tag.endswith('tbl'):
                table = Table(element, self.doc)
                md_table = self._parse_table(table)
                if md_table.strip():
                    markdown_content.append(md_table)

        return page_count, "\n\n".join(markdown_content)

    def _parse_paragraph(self, para: Paragraph) -> str:
        """
        Преобразует параграф в Markdown, обрабатывая стили.
        Изображения пропускаются.
        """
        # Определение стиля заголовка
        style_name = para.style.name if para.style else ""
        prefix = ""
        if style_name.startswith('Heading 1'): prefix = "# "
        elif style_name.startswith('Heading 2'): prefix = "## "
        elif style_name.startswith('Heading 3'): prefix = "### "

        # Сбор только текста
        full_text_parts = []

        for run in para.runs:
            text = run.text
            if text:
                full_text_parts.append(text)
            # Логика извлечения картинок полностью удалена

        text_content = "".join(full_text_parts)

        # Если это список
        if para.style and 'List' in (para.style.name or ''):
            text_content = f"- {text_content}"

        result = f"{prefix}{text_content}"

        return result

    def _parse_table(self, table: Table) -> str:
        """
        Преобразует таблицу Word в Markdown таблицу.
        """
        md_rows = []
        is_first = True

        for row in table.rows:
            cells = []
            for cell in row.cells:
                # Очищаем текст от лишних пробелов и новых строк
                cell_text = cell.text.replace("\n", " ").strip()
                cells.append(cell_text)

            # Формирование строки markdown
            md_row = "| " + " | ".join(cells) + " |"
            md_rows.append(md_row)

            # Добавление разделителя после заголовка
            if is_first:
                separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                md_rows.append(separator)
                is_first = False

        return "\n".join(md_rows)

    # Методы _get_drawing_from_run и _extract_image удалены как неиспользуемые