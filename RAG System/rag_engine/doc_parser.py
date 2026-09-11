import os
import tempfile
import uuid
import win32com.client

from .docx_parser import DocxParser, _WORD_LOCK, _ensure_com, _teardown_com


class DocParser:
    """
    Парсер для .doc (Word 97‑2003).
    Все обращения к Word COM сериализуются общим локом _WORD_LOCK
    (тот же, что у DocxParser), чтобы Word не завис при параллельной
    индексации.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    def parse(self):
        temp_docx_path = None
        word_app = None
        doc = None

        with _WORD_LOCK:
            _ensure_com()
            try:
                word_app = win32com.client.Dispatch("Word.Application")
                word_app.Visible = False
                word_app.ScreenUpdating = False
                word_app.DisplayAlerts = 0  # wdAlertsNone — без модальных диалогов

                temp_dir = tempfile.gettempdir()
                temp_docx_path = os.path.join(temp_dir, f"temp_{uuid.uuid4()}.docx")

                # Конвертируем .doc → .docx
                abs_source_path = os.path.abspath(self.file_path)
                doc = word_app.Documents.Open(
                    abs_source_path,
                    ReadOnly=True,
                    AddToRecentFiles=False,
                    ConfirmConversions=False,
                )
                doc.SaveAs2(temp_docx_path, FileFormat=16)   # 16 = wdFormatXMLDocument
                doc.Close(False)

                # Парсим полученный .docx
                parser = DocxParser(temp_docx_path)
                return parser.parse()

            except Exception as exc:
                raise RuntimeError(f"Ошибка конвертации/парсинга .doc: {exc}")

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

                if temp_docx_path and os.path.exists(temp_docx_path):
                    try:
                        os.remove(temp_docx_path)
                    except OSError:
                        pass