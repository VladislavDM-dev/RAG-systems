from rag_engine.file_hash_manager import FileHashManager


def test_db_init_creates_file(tmp_path):
    db_path = str(tmp_path / "hashes.db")
    mgr = FileHashManager(db_path)
    assert (tmp_path / "hashes.db").exists()


def test_save_and_get(tmp_path):
    mgr = FileHashManager(db_path=str(tmp_path / "h.db"))
    mgr.save("C:\\doc1.docx", "abc123")
    assert mgr.get("C:\\doc1.docx") == "abc123"
    assert mgr.exists("C:\\doc1.docx")


def test_get_missing_returns_none(tmp_path):
    mgr = FileHashManager(db_path=str(tmp_path / "h.db"))
    assert mgr.get("missing.docx") is None


def test_save_overwrites(tmp_path):
    mgr = FileHashManager(db_path=str(tmp_path / "h.db"))
    mgr.save("C:\\doc1.docx", "old")
    mgr.save("C:\\doc1.docx", "new")
    assert mgr.get("C:\\doc1.docx") == "new"


def test_remove(tmp_path):
    mgr = FileHashManager(db_path=str(tmp_path / "h.db"))
    mgr.save("C:\\doc1.docx", "abc")
    mgr.remove("C:\\doc1.docx")
    assert not mgr.exists("C:\\doc1.docx")


def test_get_all_paths_and_hashes(tmp_path):
    mgr = FileHashManager(db_path=str(tmp_path / "h.db"))
    mgr.save("b.docx", "2")
    mgr.save("a.docx", "1")
    mgr.save("c.docx", "3")
    assert mgr.get_all_paths() == ["a.docx", "b.docx", "c.docx"]
    assert mgr.get_all_hashes() == {"a.docx": "1", "b.docx": "2", "c.docx": "3"}