import os
import tempfile
import uuid
import time
import subprocess

import PyPDF2

from .docx_parser import DocxParser


class PdfParser:
    r"""
    Парсер PDF через конвертацию в DOCX с помощью ABBYY FineReader 15.
    Работает только если в системе установлен FineReader 15
    и находится исполняемый файл  C:\Program Files (x86)\ABBYY FineReader 15\FineCmd.exe
    """
    # Путь к исполняемому файлу FineCmd.exe
    _FINEREADER_EXE = r"C:\Program Files (x86)\ABBYY FineReader 15\FineCmd.exe"

    def __init__(self, file_path: str, language: str = "Russian+English"):
        """
        :param file_path: Путь к исходному PDF
        :param language: Язык(ы) для OCR (по умолчанию – ru)
        """
        self.file_path = os.path.abspath(file_path)
        self.language = language

        if not os.path.isfile(self._FINEREADER_EXE):
            raise RuntimeError(
                f"FineCmd.exe не найден по пути: {self._FINEREADER_EXE}"
            )

        if not os.path.isfile(self.file_path):
            raise FileNotFoundError(f"Исходный PDF не найден: {self.file_path}")

    # ------------------------------------------------------------------
    #  Внутренние helpers
    # ------------------------------------------------------------------
    def _convert_pdf_to_docx(self, out_path: str) -> None:
        """
        Запускает FineReaderOCR.exe и конвертирует PDF в DOCX.
        Генерирует подробный вывод в stdout; при ошибке выбрасывает RuntimeError.
        """
        cmd = [
            self._FINEREADER_EXE,
            self.file_path,
            "/out", out_path,
            "/lang", self.language,
            "/quit"
        ]

        # В некоторых версиях FineReader нужно явно указать язык по-английски,
        # даже если основной язык – ru. Поэтому можно добавить /language ru,en
        # cmd.append("/language")
        # cmd.append("ru,en")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                check=True          # raise CalledProcessError при non‑zero exit
            )
        except subprocess.CalledProcessError as exc:
            # Код возврата != 0
            raise RuntimeError(
                f"FineReaderOCR завершился с ошибкой (код {exc.returncode}). "
                f"Вывод:\n{exc.stdout}"
            )

        # Проверка, что файл действительно появился
        if not os.path.exists(out_path):
            raise RuntimeError("FineReaderOCR не создал DOCX после конвертации.")

    # ------------------------------------------------------------------
    #  Публичный API
    # ------------------------------------------------------------------
    def parse(self):

        page_count = self.get_page_count(self.file_path)
        if page_count == 0 or page_count > 10:
            return page_count, None
        """
        Конвертирует PDF в DOCX при помощи FineReader и возвращает
        текст, извлечённый из DOCX с помощью DocxParser.
        """
        temp_docx_path = None
        try:
            # Создаём временный файл‑назначение
            temp_dir = tempfile.gettempdir()
            unique_name = f"fr_out_{uuid.uuid4()}.docx"
            temp_docx_path = os.path.join(temp_dir, unique_name)

            # Конвертируем
            self._convert_pdf_to_docx(temp_docx_path)

            # Парсим полученный DOCX
            parser = DocxParser(temp_docx_path)
            return parser.parse(False,page_count)

        except Exception as e:
            return page_count, None

        finally:
            # Очистка временного файла
            if temp_docx_path and os.path.exists(temp_docx_path):
                try:
                    time.sleep(0.1)
                    os.remove(temp_docx_path)
                except OSError:
                    pass

    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        with open(pdf_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            return len(pdf_reader.pages)