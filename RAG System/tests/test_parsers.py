import pytest

from rag_engine.docx_parser import DocxParser


def _list_docx(out_dir):
    return sorted(out_dir.glob("*.docx"))


def test_out_dir_has_docx(out_dir):
    assert _list_docx(out_dir), "Каталог out должен содержать .docx файлы"


def test_parse_all_docx_files(out_dir):
    """Парсим каждый из 49 docx: страница>0, текст есть, есть кириллица."""
    files = _list_docx(out_dir)
    assert len(files) >= 49

    for f in files:
        page_count, text = DocxParser(str(f)).parse()
        assert page_count > 0, f"Страницы не распознаны: {f.name}"
        assert text, f"Пустой текст: {f.name}"
        cyrillic = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF)
        assert cyrillic > 10, f"Подозрительно мало кириллицы в {f.name}"


def test_parse_specific_metadata(out_dir):
    """В служебной записке #20 должен быть номер и дата."""
    target = out_dir / "#20-2026.02.18-О реорганизации работы отдела.docx"
    assert target.exists()
    page_count, text = DocxParser(str(target)).parse()
    assert "20" in text
    assert "18.02.2026" in text


def test_parse_missing_file_raises():
    from docx import Document  # поднимается при инициализации DocxParser

    with pytest.raises(Exception):
        DocxParser(r"Z:\несуществующий\файл.docx")