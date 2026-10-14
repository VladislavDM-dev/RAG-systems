# -*- coding: utf-8 -*-
"""Нормализация русского текста: лемматизация для гибридного BM25+FAISS поиска.

pymorphy3 приводит слово к базовой форме (лемме): «канцелярских» → «канцелярский»,
«закупке» → «закупка». BM25 строится по леммам — морфологические варианты
склеиваются, опечатки в словоформе перестают ломать точное совпадение токена.
Если pymorphy3 недоступен — fallback на lowercase без лемматизации.
"""
import re
from functools import lru_cache

_morph = None
_morph_broken = False


def _get_morph():
    global _morph, _morph_broken
    if _morph is None and not _morph_broken:
        try:
            import pymorphy3
            _morph = pymorphy3.MorphAnalyzer()
        except Exception:
            _morph_broken = True
    return _morph


_WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


@lru_cache(maxsize=100_000)
def lemmatize_word(word: str) -> str:
    """Лемматизирует одно слово (кэш до 100k слов — индекс стабилен)."""
    w = (word or "").lower()
    if not w:
        return w
    morph = _get_morph()
    if morph is None:
        return w
    try:
        parsed = morph.parse(w)
        if parsed:
            return parsed[0].normal_form
    except Exception:
        pass
    return w


def lemmatize_text(text: str) -> str:
    """Лемматизирует текст, сохраняя порядок слов. Нелемматизируемые токены — как есть."""
    words = _WORD_RE.findall(text or "")
    return " ".join(lemmatize_word(w) for w in words)


def tokenize_lemmas(text: str) -> list:
    """Токенизация + лемматизация — вход для BM25Okapi.get_scores()."""
    return lemmatize_text(text).split()
