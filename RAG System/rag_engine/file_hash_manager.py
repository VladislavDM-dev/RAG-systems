from sqlite3 import connect, Connection
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class FileInfo:
    path: str
    hash: str
    modified: datetime = field(default_factory=datetime.now)

class FileHashManager:
    def __init__(self, db_path: str = ".cache/file_hashes.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Инициализация БД и открытие соединения"""
        self.conn = connect(self.db_path, check_same_thread=False)
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_hashes (
                    path TEXT PRIMARY KEY,
                    hash TEXT NOT NULL,
                    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.conn.commit()
        except Exception as e:
            print(f"[FileHashManager] Ошибка инициализации БД: {e}")
            if self.conn:
                self.conn.close()
                self.conn = None

    def close(self):
        """Закрыть соединение с БД (освобождает файл для удаления)."""
        if self.conn:
            try:
                self.conn.close()
            except Exception as e:
                print(f"[FileHashManager] Ошибка при закрытии: {e}")
            finally:
                self.conn = None

    def __del__(self):
        """Закрытие соединения при удалении объекта"""
        self.close()

    def save(self, path: str, hash: str):
        """Сохранить или обновить хэш по path"""
        if not self.conn:
            self._init_db()
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO file_hashes (path, hash, modified) VALUES (?, ?, datetime('now'))",
                    (path, hash)
                )
        except Exception as e:
            print(f"[FileHashManager] Ошибка сохранения: {e}")
            raise

    def get(self, path: str) -> str | None:
        """Получить хэш по path"""
        if not self.conn:
            self._init_db()
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT hash FROM file_hashes WHERE path = ?", (path,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"[FileHashManager] Ошибка получения: {e}")
            return None

    def remove(self, path: str):
        """Удалить запись по path"""
        if not self.conn:
            self._init_db()
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM file_hashes WHERE path = ?", (path,))
        except Exception as e:
            print(f"[FileHashManager] Ошибка удаления: {e}")
            raise

    def get_all_paths(self) -> list[str]:
        """Получить список всех сохранённых путей"""
        if not self.conn:
            self._init_db()
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT path FROM file_hashes ORDER BY path")
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"[FileHashManager] Ошибка получения путей: {e}")
            return []

    def get_all_hashes(self) -> dict[str, str]:
        """Получить все хэши в виде словаря"""
        paths = self.get_all_paths()
        return {p: self.get(p) for p in paths}

    def exists(self, path: str) -> bool:
        """Проверить существование записи"""
        return self.get(path) is not None