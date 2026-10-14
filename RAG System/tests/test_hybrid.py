# -*- coding: utf-8 -*-
"""Тесты лемматизации (text_norm) и гибридного BM25+FAISS ретрива."""
import pytest


# ---------------------------------------------------------------------------
#  text_norm: лемматизация
# ---------------------------------------------------------------------------
def test_lemmatize_word_basic():
    from rag_engine.text_norm import lemmatize_word
    assert lemmatize_word("канцелярских") == "канцелярский"
    assert lemmatize_word("закупке") == "закупка"
    assert lemmatize_word("бумага") == "бумага"
    assert lemmatize_word("БУМАГА") == "бумага"


def test_lemmatize_word_empty():
    from rag_engine.text_norm import lemmatize_word
    assert lemmatize_word("") == ""
    assert lemmatize_word(None) == ""


def test_lemmatize_text():
    from rag_engine.text_norm import lemmatize_text
    result = lemmatize_text("о закупке канцелярских принадлежностей")
    assert result == "о закупка канцелярский принадлежность"


def test_tokenize_lemmas():
    from rag_engine.text_norm import tokenize_lemmas
    tokens = tokenize_lemmas("Служебная записка о закупке бумаги")
    assert "служебный" in tokens or "служебная" in tokens  # pymorphy может дать разные варианты
    assert "закупка" in tokens
    assert "бумага" in tokens


# ---------------------------------------------------------------------------
#  BM25 build / save / load
# ---------------------------------------------------------------------------
def test_build_bm25_empty_index(tmp_path, monkeypatch):
    """Пустой docstore → BM25 не строится, но не падает."""
    from rag_engine.rag_engine import RAGEngine

    eng = RAGEngine.__new__(RAGEngine)
    eng.cache_dir = str(tmp_path)
    eng.index = None
    eng.bm25 = None
    eng.bm25_ids = []

    eng._build_bm25()
    assert eng.bm25 is None
    assert eng.bm25_ids == []


def test_bm25_save_load_roundtrip(tmp_path):
    """BM25 сохраняется и загружается из кэша."""
    from rag_engine.rag_engine import RAGEngine
    from rag_engine.text_norm import tokenize_lemmas
    from rank_bm25 import BM25Okapi

    eng = RAGEngine.__new__(RAGEngine)
    eng.cache_dir = str(tmp_path)
    eng.bm25 = BM25Okapi([
        tokenize_lemmas("закупка канцелярских принадлежностей"),
        tokenize_lemmas("служебная записка об отпуске"),
    ])
    eng.bm25_ids = ["node-1", "node-2"]

    eng._save_bm25()

    eng2 = RAGEngine.__new__(RAGEngine)
    eng2.cache_dir = str(tmp_path)
    eng2.bm25 = None
    eng2.bm25_ids = []

    assert eng2._load_bm25() is True
    assert eng2.bm25 is not None
    assert eng2.bm25_ids == ["node-1", "node-2"]


def test_bm25_load_missing_files(tmp_path):
    """Нет файлов кэша → _load_bm25 возвращает False."""
    from rag_engine.rag_engine import RAGEngine

    eng = RAGEngine.__new__(RAGEngine)
    eng.cache_dir = str(tmp_path)
    eng.bm25 = None
    eng.bm25_ids = []

    assert eng._load_bm25() is False
