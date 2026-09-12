"""Генерация служебной записки (.docx) по шаблону mmo.dotx.

Структура полей определяется СЕРВЕРОМ из самого файла шаблона: при чтении
memo.dotx ищутся все плейсхолдеры вида {{ key }} в тексте документа и таблицах.
Если файл шаблона изменился (даже без перезапуска WebUI) — поля подхватываются
автоматически (кэш по mtime). Админ может перезагрузить шаблон кнопкой или
загрузить новый файл через API.
"""
import io
import os
import re
import shutil
import tempfile
import zipfile

from docx import Document

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMPLATE_DIR = os.environ.get(
    "MEMO_TEMPLATE_DIR",
    os.path.join(PROJECT_ROOT, "docx_templates"),
)

TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, "mmo.dotx")

# Запасные поля, если шаблон недоступен или пуст.
DEFAULT_FIELDS = [
    "recipient_position",
    "recipient_name",
    "memo_number",
    "date",
    "body",
    "sender_position",
    "sender_short_name",
]

FIELD_LABELS = {
    "recipient_position": "Кому (должность)",
    "recipient_name": "Кому (ФИО)",
    "memo_number": "Номер служебной записки",
    "department": "Отдел",
    "date": "Дата",
    "body": "Текст служебной записки",
    "sender_position": "От (должность)",
    "sender_short_name": "От (ФИО, кратко)",
    "executor": "ФИО исполнителя",
    "phone": "Телефон исполнителя",
}

FIELD_HINTS = {
    "body": "оставьте пустым — сгенерируем по RAG",
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

_cache = {"mtime": None, "fields": DEFAULT_FIELDS, "exists": False}


def _fix_content_type(src: str, dst: str) -> None:
    """Копирует .dotx в .docx, заменив content-type document.xml."""
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                text = data.decode("utf-8")
                text = text.replace(
                    "wordprocessingml.template.main+xml",
                    "wordprocessingml.document.main+xml",
                )
                data = text.encode("utf-8")
            zout.writestr(item, data)


def _all_parts(doc):
    """Генерирует (абзац) по абзацам, таблицам и header/footer документа."""
    seen = set()
    for p in doc.paragraphs:
        yield p
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
    for section in doc.sections:
        for part in (section.header, section.footer):
            if part.is_linked_to_previous:
                continue
            for p in part.paragraphs:
                yield p
            for table in part.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for p in cell.paragraphs:
                            yield p


def _iterate_all_text(doc):
    """Проходит по абзацам и всем ячейкам таблиц документа (включая header/footer)."""
    for p in _all_parts(doc):
        yield p.text or ""


def discover_template_fields(path: str) -> list:
    """Извлекает упорядоченный список полей {{ key }} из файла шаблона."""
    if not os.path.exists(path):
        return []
    workdir = tempfile.gettempdir()
    src = path
    tmp = os.path.join(workdir, "memo_discover.docx")
    if path.lower().endswith(".dotx"):
        try:
            _fix_content_type(path, tmp)
            src = tmp
        except Exception:
            src = path
    doc = Document(src)
    seen = []
    for text in _iterate_all_text(doc):
        for m in _PLACEHOLDER_RE.finditer(text):
            key = m.group(1)
            if key not in seen:
                seen.append(key)
    return seen


def _fields_exist(path: str) -> bool:
    return os.path.exists(path)


def get_template_fields() -> list:
    """Возвращает поля шаблона. Кэширует по mtime файла, поэтому изменившийся
    шаблон подхватывается без перезапуска WebUI."""
    try:
        mtime = os.path.getmtime(TEMPLATE_PATH)
    except OSError:
        mtime = None

    if mtime is not None and _cache["mtime"] == mtime and _cache["fields"]:
        return _cache["fields"]

    fields = discover_template_fields(TEMPLATE_PATH)
    if not fields and mtime is not None:
        fields = DEFAULT_FIELDS

    _cache["mtime"] = mtime
    _cache["fields"] = fields or DEFAULT_FIELDS
    _cache["exists"] = mtime is not None
    return _cache["fields"]


def reload_template_fields() -> list:
    """Принудительно перечитывает шаблон (кнопка админа)."""
    _cache["mtime"] = None
    return get_template_fields()


def save_template_file(file_bytes: bytes) -> list:
    """Сохраняет загруженный админом шаблон и перечитывает поля."""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    with open(TEMPLATE_PATH, "wb") as f:
        f.write(file_bytes)
    return reload_template_fields()


def get_template_info() -> dict:
    """Информация о шаблоне: путь, mtime, размер, поля."""
    fields = get_template_fields()
    try:
        st = os.stat(TEMPLATE_PATH)
        mtime = __import__("datetime").datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        size = st.st_size
    except OSError:
        mtime = None
        size = None
    return {
        "path": TEMPLATE_PATH,
        "template_dir": TEMPLATE_DIR,
        "updated": mtime,
        "size": size,
        "fields": fields,
        "labels": FIELD_LABELS,
        "hints": FIELD_HINTS,
    }


def _replace_paragraph_text(p, text):
    for r in p.runs:
        r.text = ""
    if p.runs:
        p.runs[0].text = text
    else:
        p.add_run(text)


def _insert_paragraph_after(paragraph, text):
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    np = Paragraph(new_p, paragraph._parent)
    np.add_run(text)
    return np


def generate_memo_docx(fields: dict) -> io.BytesIO:
    """Собирает .docx из шаблона с подставленными полями."""
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Шаблон служебной записки не найден: {TEMPLATE_PATH}")

    workdir = tempfile.gettempdir()
    tmp = os.path.join(workdir, "memo_template.docx")
    _fix_content_type(TEMPLATE_PATH, tmp)

    doc = Document(tmp)
    template_fields = get_template_fields()

    def substitute(text):
        for key in template_fields:
            text = text.replace("{{ %s }}" % key, (fields.get(key) or ""))
        return text

    paragraphs = list(doc.paragraphs)
    # Подставляем поля во все абзацы документа (включая таблицы и header/footer).
    for p in _all_parts(doc):
        full = p.text or ""
        if "{{" not in full:
            continue
        # Текущий абзац — тело ({{ body }}), разбиваем на несколько абзацев.
        if "{{ body }}" in full:
            body_lines = [ln for ln in (fields.get("body") or "").split("\n") if ln.strip()]
            if body_lines:
                _replace_paragraph_text(p, body_lines[0])
                anchor = p
                for line in body_lines[1:]:
                    anchor = _insert_paragraph_after(anchor, line)
            else:
                _replace_paragraph_text(p, "")
            continue
        _replace_paragraph_text(p, substitute(full))

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out