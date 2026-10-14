import gc
import os
import re
import sys
import time
import json
import shutil
import hashlib
import threading
from pathlib import Path
from typing import List, Optional

import faiss
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    Settings as LlamaSettings,
    PromptTemplate,
    Document,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeWithScore
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.vector_stores.faiss import FaissVectorStore
from datetime import datetime

from .config import Settings
from .doc_parser import DocParser
from .docx_parser import DocxParser
from .pdf_parser import PdfParser
from .file_hash_manager import FileHashManager
from .providers import create_provider


_MEMO_BATCH_SYSTEM_PROMPT = (
    "Ты — RAG-ассистент по служебным запискам. По теме «{topic}» определи "
    "служебные записки, релевантные теме, среди приведённых фрагментов "
    "документов (это батч №{page_no}). Каждый фрагмент помечен строкой "
    "[Файл: <полный путь>]. Ранее уже были найдены файлы: {previously}. "
    "Работай кратко и по делу, не размышляй вслух — LLM-поток отдельный: "
    "в этой генерации выводи ТОЛЬКО итоговый список. Выведи лишь полные пути "
    "(из меток [Файл: ...]) записок, релевантных теме, которых ещё не было "
    "в списке ранее найденных. НЕ описывай ход проверки, НЕ комментируй каждый "
    "фрагмент, НЕ повторяй пути, НЕ перечисляй нерелевантные — сразу ответь "
    "списком, по одному пути на строку:\nПУТЬ: <полный путь>\n"
    "Если в этом батче нет новых релевантных записок — ответь ровно: "
    "НОВЫХ ЗАПИСОК НЕТ"
)


def _count_tokens(*texts: str) -> int:
    """Оценка количества токенов через tiktoken (cl100k_base).

    При недоступности энкодера — грубая оценка 4 символа на токен.
    """
    total = 0
    enc = None
    for t in texts:
        t = t or ""
        if not t:
            continue
        if enc is None:
            try:
                import tiktoken
                enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                enc = False
        if enc:
            try:
                total += len(enc.encode(t))
            except Exception:
                total += max(1, len(t) // 4)
        else:
            total += max(1, len(t) // 4)
    return total


class _ExcludeNodeIdsPostprocessor(BaseNodePostprocessor):
    """Postprocessor: выкидывает из ретрива узлы, уже отданные ранее.

    Нужен для постраничного (batch-by-batch) обхода индекса: потребитель
    передаёт node_id уже полученных кусков, а ядро возвращает следующие.
    """

    def __init__(self, exclude_ids: List[str]):
        super().__init__()
        self._exclude_ids = set(exclude_ids)

    @classmethod
    def class_name(cls) -> str:
        return "ExcludeNodeIdsPostprocessor"

    def _postprocess_nodes(self, nodes, query_bundle=None):
        return [n for n in nodes if n.node.node_id not in self._exclude_ids]


class RAGEngine:
    """RAG-движок: индексация документов и поиск по ним."""

    VERSION = "26.10.14"

    def __init__(self, config: Optional[Settings] = None):
        self.cfg = config or Settings()
        self.version = self.VERSION
        self.documents_paths = list(self.cfg.sync_folders or [])
        if getattr(sys, "frozen", False):
            # В frozen-сборке .cache кладём рядом с exe, а не в cwd.
            self.cache_dir = str(Path(sys.executable).resolve().parent / ".cache")
        else:
            self.cache_dir = ".cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.index = None
        self.node_parser = SentenceSplitter(
            chunk_size=self.cfg.chunk_size,
            chunk_overlap=self.cfg.chunk_overlap,
            paragraph_separator="\n\n\n",
        )
        self.file_hash_db = FileHashManager(os.path.join(self.cache_dir, "file_hashes.db"))
        self.provider = create_provider(self.cfg.provider, self.cfg.url, self.cfg.api_key)

        # Статус
        self.status_backend = False
        self.backend_models = []
        self.backend_models_thinking = []
        self.backend_models_embed = []
        self.is_syncing = False
        self.is_initialized = False
        self.sync_status = "Ожидание запуска..."
        self.sync_progress = 0
        self.sync_start_time = 0
        self.sync_file = []
        self.items_processed = 0
        self.avg_time_per_item = 0.0

        self.cfg.save()

    # ------------------------------------------------------------------
    #  Компоненты
    # ------------------------------------------------------------------
    def _ensure_cache_dir(self):
        os.makedirs(self.cache_dir, exist_ok=True)

    @staticmethod
    def _calculate_file_hash(filepath: str) -> str:
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _scan_documents(self):
        """Сканирует sync_folders и возвращает (new_or_modified, deleted, current_hashes)."""
        current_hashes = {}
        new_or_modified = []
        all_files = []

        for base in self.documents_paths:
            if not os.path.exists(base):
                continue
            self.sync_status = "Поиск файлов..."
            for root, _, filenames in os.walk(base):
                for file in filenames:
                    if file.startswith("~") or file.endswith(".tmp"):
                        continue
                    if not (
                        file.endswith(".doc")
                        or file.endswith(".docx")
                        or file.endswith(".pdf")
                    ):
                        continue
                    full_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(full_path)
                        if size > self.cfg.size_limit_mb * 1024 * 1024:
                            continue
                    except OSError:
                        continue
                    all_files.append(full_path)

        total_files = len(all_files) or 1
        for i, full_path in enumerate(all_files):
            try:
                file_hash = self._calculate_file_hash(full_path)
                prev_hash = self.file_hash_db.get(full_path)
                if prev_hash is None or prev_hash != file_hash:
                    new_or_modified.append(full_path)
                current_hashes[full_path] = file_hash
                progress = 3 + int((i + 1) / total_files * 2)
                self.sync_progress = progress
                self.sync_status = f"Сканирование файлов ({i + 1}/{total_files})..."
            except Exception as e:
                print(f"Error reading {full_path}: {e}")

        return new_or_modified, [], current_hashes

    def _load_document(self, full_path: str) -> Optional[Document]:
        if not os.path.exists(full_path):
            print(f"[WARN] Файл не найден: {full_path}")
            return None
        try:
            ext = os.path.splitext(full_path)[1].lower()
            if ext == ".docx":
                parser = DocxParser(full_path)
            elif ext == ".doc":
                parser = DocParser(full_path)
            elif ext == ".pdf":
                parser = PdfParser(full_path)
            else:
                reader = SimpleDirectoryReader(input_files=[full_path], filename_as_id=True)
                docs = reader.load_data()
                if not docs:
                    return None
                text = docs[0].text

            if ext in {".docx", ".doc", ".pdf"}:
                page_count, text = parser.parse()
                if page_count == 0:
                    print(f"[WARN] Не удалось прочитать количество страниц: {full_path}")
                    return None
                if page_count > self.cfg.page_limit:
                    print(f"[WARN] Количество страниц > {self.cfg.page_limit}: {full_path}")
                    return None
                if text is None:
                    print(f"[WARN] Не удалось прочитать файл: {full_path}")
                    return None

            return Document(
                text=text,
                metadata={"file_name": full_path, "file_path": full_path},
            )
        except Exception as e:
            print(f"[ERROR] Ошибка при чтении {full_path}: {e}")
            return None

    def _remove_nodes_for_files(self, deleted_files: List[str]) -> int:
        if not self.index or not deleted_files:
            return 0
        count = 0
        for file_rel_path in deleted_files:
            try:
                self.index.delete_ref_doc(file_rel_path, delete_from_docstore=True)
                count += 1
            except Exception:
                pass
        return count

    # ------------------------------------------------------------------
    #  Синхронизация индекса
    # ------------------------------------------------------------------
    def sync_index(self, is_remove: bool = False):
        """Синхронизация индекса по файлам. Потокобезопасна (запускать в потоке)."""
        if self.is_syncing:
            return
        self.is_syncing = True
        self.sync_start_time = time.time()
        self.sync_status = "Инициализация моделей..."
        self.sync_progress = 5
        self.items_processed = 0
        self.avg_time_per_item = 0.0
        self.sync_file = []

        if is_remove:
            if self.file_hash_db:
                self.file_hash_db.close()
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            os.makedirs(self.cache_dir, exist_ok=True)
            self.file_hash_db = FileHashManager(os.path.join(self.cache_dir, "file_hashes.db"))

        try:
            # Загрузка существующего индекса или создание нового
            try:
                vector_store = FaissVectorStore.from_persist_dir(self.cache_dir + "/faiss_index")
                storage_context = StorageContext.from_defaults(
                    vector_store=vector_store,
                    persist_dir=self.cache_dir + "/faiss_index",
                )
                self.index = load_index_from_storage(storage_context)
                self.sync_status = "Кэш индекса загружен."
                print("✅ Кэш индекса загружен.")
            except Exception as e:
                faiss_store = faiss.IndexFlatL2(self.cfg.embedding_dim)
                vector_store = FaissVectorStore(faiss_index=faiss_store)
                storage_context = StorageContext.from_defaults(vector_store=vector_store)
                storage_context.persist(persist_dir=self.cache_dir + "/faiss_index")
                self.sync_status = "Индекс инициализирован с нуля."
                self.index = VectorStoreIndex(
                    nodes=[],
                    embed_model=LlamaSettings.embed_model,
                    storage_context=storage_context,
                )
                print("⚠️ Индекс инициализирован с нуля")

            new_or_modified, deleted, current_hashes = self._scan_documents()

            if deleted:
                self.sync_status = f"Удаление {len(deleted)} устаревших файлов..."
                for i, f in enumerate(deleted):
                    self._remove_nodes_for_files([f])
                    self.file_hash_db.remove(f)
                    self.sync_progress = 2 + int((i + 1) / len(deleted) * 3)

            total_files = len(new_or_modified)
            if total_files == 0:
                self.sync_status = "Новых или изменённых файлов нет."
                self.sync_progress = 100
                self.is_initialized = True
                return

            self.sync_status = f"Обработка {total_files} файлов..."
            self.sync_progress = 5
            self.sync_file = []
            lock = threading.Lock()
            items_processed = 0

            def _update_sync_file(rel_path: str, operation: str):
                with lock:
                    entry = next((e for e in self.sync_file if e["file"] == rel_path), None)
                    if entry:
                        entry["operation"] = operation
                    else:
                        self.sync_file.append({"file": rel_path, "operation": operation})

            def _process_file(rel_path: str):
                nonlocal items_processed
                file_name = os.path.basename(rel_path)

                _update_sync_file(file_name, "Загрузка и парсинг...")
                with lock:
                    doc = self._load_document(rel_path)
                    if doc is None:
                        self.sync_file = [e for e in self.sync_file if e["file"] != file_name]
                        items_processed += 1
                        self.sync_progress = 10 + int(items_processed / total_files * 80)
                        self.sync_status = f"Обработано {items_processed}/{total_files} файлов."
                        return

                _update_sync_file(file_name, "Разбиваем на узлы...")
                nodes = self.node_parser.get_nodes_from_documents([doc])

                _update_sync_file(file_name, "Вставляем в индекс...")
                with lock:
                    self.index.insert_nodes(nodes)
                    self.index.storage_context.persist(
                        persist_dir=self.cache_dir + "/faiss_index"
                    )

                del nodes, doc
                gc.collect()

                _update_sync_file(file_name, "Обновляем метаданные...")
                with lock:
                    self.file_hash_db.save(rel_path, current_hashes[rel_path])

                with lock:
                    items_processed += 1
                    self.sync_progress = 10 + int(items_processed / total_files * 80)
                    self.sync_status = f"Обработано {items_processed}/{total_files} файлов."

                with lock:
                    self.sync_file = [e for e in self.sync_file if e["file"] != file_name]

            # Обработка строго последовательная: FaissVectorStore.insert_nodes +
            # persist при параллельной записи из нескольких потоков конкурируют
            # за один файл индекса и могут зависать/портить FAISS.
            for rel_path in new_or_modified:
                try:
                    _process_file(rel_path)
                except Exception as exc:
                    print(f"[ERROR] Обработка {rel_path} завершилась с ошибкой: {exc}")

            self.sync_status = "Сохранение финального кэша..."
            self.sync_progress = 95
            storage_context.persist(persist_dir=self.cache_dir + "/faiss_index")

            self.is_initialized = True
            self.sync_progress = 100
            self.sync_status = "Готово к работе"
            print("✅ Система полностью инициализирована.")

        except Exception as e:
            self.sync_status = f"Ошибка: {e}"
            print(f"Sync error: {e}")
        finally:
            self.is_syncing = False

    # ------------------------------------------------------------------
    #  Модели / провайдер
    # ------------------------------------------------------------------
    def __init_backend(self):
        print(f"🔄 Настройка моделей провайдера '{self.cfg.provider}'...")
        try:
            LlamaSettings.llm = self.provider.build_llm(
                self.cfg.llm,
                self.cfg.context_window,
                temperature=0.98,
            )
            LlamaSettings.embed_model = self.provider.build_embed_model(self.cfg.llm_embed)
            print("✅ Модели настроены.")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка настройки моделей (проверьте запущен ли {self.cfg.provider}): {e}")
            return False

    def initialize(self):
        self.__init_backend()
        self.__check_backend()
        thread = threading.Thread(target=self.sync_index, daemon=True)
        thread.start()
        print("🚀 Поток синхронизации запущен.")

    def __check_backend(self):
        try:
            models = self.provider.list_models()
            self.backend_models = models
            self.status_backend = True
            self.backend_models_thinking = [
                m for m in models
                if self.provider.capabilities(m, "thinking")
            ]
            self.backend_models_embed = [
                m for m in models
                if self.provider.capabilities(m, "embedding")
            ]
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка: {e}")
            self.status_backend = False
            # Бэкенд недоступен (например, указан адрес на другой машине) —
            # не оставляем списки моделей от прежнего провайдера/адреса,
            # иначе админка показывает устаревшие модели.
            self.backend_models = []
            self.backend_models_thinking = []
            self.backend_models_embed = []


    # ------------------------------------------------------------------
    #  Запросы внешних агентов
    # ------------------------------------------------------------------
    DEFAULT_AGENT_SYSTEM_PROMPT = (
        "Ты — RAG-ассистент, отвечающий на основе предоставленных документов. "
        "Отвечай на вопрос, опираясь только на информацию из контекста ниже. "
        "Если в контексте нет нужных данных, честно скажи, что информации нет. "
        "Не выдумывай факты, не упоминай документы, которых нет в контексте."
    )

    def agent_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        top_k: Optional[int] = None,
        temperature: Optional[float] = None,
        exclude_node_ids: Optional[List[str]] = None,
    ):
        """Генератор SSE-событий для внешних агентов.

        Поиск по индексу (RAG) + ответ LLM с учётом системного промпта агента.
        События: token / reasoning(thinking) / sources / done / error.

        Финальный промпт собирается вручную (ретрив + упаковка контекста), а
        генерация идёт через прямой `llm.stream_chat` — в отличие от синтеза
        query_engine (compact) его `response_gen` отдаёт только текст и теряет
        «размышления» модели. Здесь каждый ChunkResponse несёт и текстовый delta
        (событие `token`), и reasoning delta (`additional_kwargs["thinking_delta"]`,
        событие `reasoning`) — как у OpenAI-совместимых reasoning-моделей, так и
        у Ollama.

        exclude_node_ids: node_id фрагментов, уже отданных потребителю.
        Ключевые фрагменты этих id исключаются из ретрива — так можно
        «листать» индекс пачками по top_k, не повторяя уже полученное.
        """
        if self.is_syncing:
            yield {"type": "error", "data": "Идет синхронизация"}
            return
        if not self.is_initialized or self.index is None:
            yield {"type": "error", "data": "Индекс не готов"}
            return
        if not prompt or not str(prompt).strip():
            yield {"type": "error", "data": "Поле 'prompt' обязательно"}
            return

        system_prompt = (system_prompt or self.DEFAULT_AGENT_SYSTEM_PROMPT).strip()
        top_k = int(top_k or self.cfg.similarity_top_k)
        temperature = temperature if temperature is not None else 0.98
        exclude_node_ids = [str(i) for i in (exclude_node_ids or [])]

        try:
            llm = self.provider.build_llm(
                self.cfg.llm,
                self.cfg.context_window,
                temperature=temperature,
            )

            # --- 1. Ретрив с запасом и ручное исключение уже отданных node_id ---
            # Запрашиваем больше, чем top_k, потому что часть узлов отфильтруется.
            retrieval_top_k = top_k + len(exclude_node_ids)
            retriever = self.index.as_retriever(similarity_top_k=retrieval_top_k)
            nodes = retriever.retrieve(prompt)
            if exclude_node_ids:
                nodes = [n for n in nodes if n.node.node_id not in set(exclude_node_ids)]
            nodes = nodes[:top_k]

            sources = []
            for node in nodes:
                meta = node.node.metadata
                sources.append({
                    "file_name": meta.get("file_name", ""),
                    "file_path": meta.get("file_path", ""),
                    "node_id": node.node.node_id,
                    "score": round(float(getattr(node, "score", 0.0) or 0.0), 4),
                })

            # Источники известны сразу после ретрива — отдаём один раз до токенов.
            if sources:
                yield {"type": "sources", "data": sources}

            # --- 2. Упаковка контекста под окно модели ---
            node_texts = [n.node.get_content() for n in nodes]
            # Оцениваем токены как ~4 символа/токен; резервируем вывод и промпт.
            max_chars = max(0, (self.cfg.context_window - 512) * 4)
            context_parts = []
            used = 0
            for text in node_texts:
                room = max_chars - used
                if room <= 0:
                    break
                context_parts.append(text[:room].rstrip() if len(text) > room else text)
                used += len(context_parts[-1]) + 2
            context_str = "\n\n".join(context_parts)

            # --- 3. Сборка промпта (тот же вид, что давал text_qa_template) ---
            prompt_text = (
                "Системная инструкция ассистента:\n"
                + system_prompt
                + "\n-----\n"
                "Контекстная информация из документов:\n"
                + context_str
                + "\n-----\n"
                "Запрос пользователя/агента:\n"
                + prompt
                + "\n"
            )

            # --- 4. Стриминг через прямой stream_chat: текст + размышления ---
            from llama_index.core.base.llms.types import ChatMessage, MessageRole

            tokens_in = _count_tokens(prompt_text)
            full_response = []
            full_reasoning = []
            t_start = time.perf_counter()
            for resp in llm.stream_chat(
                [ChatMessage(role=MessageRole.USER, content=prompt_text)]
            ):
                token = getattr(resp, "delta", "") or ""
                if token:
                    full_response.append(token)
                    yield {"type": "token", "data": token}

                thinking = (resp.additional_kwargs or {}).get("thinking_delta")
                if thinking:
                    full_reasoning.append(thinking)
                    yield {"type": "reasoning", "data": thinking}
            elapsed_llm = time.perf_counter() - t_start

            answer_text = "".join(full_response)
            reasoning_text = "".join(full_reasoning)
            yield {
                "type": "done",
                "answer": answer_text,
                "reasoning": reasoning_text,
                "sources": sources,
                "prompt": prompt,
                "tokens_in": tokens_in,
                "tokens_out": _count_tokens(answer_text, reasoning_text),
                "elapsed": round(elapsed_llm, 2),
            }
        except Exception as e:
            yield {"type": "error", "data": str(e)}

    # ------------------------------------------------------------------
    #  Поиск всех записок по теме (по полному пути, полный текст из индекса)
    # ------------------------------------------------------------------
    def memos(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        page_size: int = 50,
        max_pages: int = 15,
    ):
        """Находит все служебные записки по теме и возвращает полный текст.

        Батчи по page_size чанков (исключая уже отданные node_id) — постраничный
        обход индекса без повторов. Полный текст каждого документа собирается
        из docstore индекса по file_path (узлы сортируются по start_char_idx) —
        файлы повторно не парсятся и Word COM не задействуется.

        Возвращает dict:
          {ok, total, pages, documents: [{file_name, file_path, text}]}
        либо {error: ...}.
        """
        result = None
        for event in self.memos_stream(prompt, temperature=temperature,
                                       page_size=page_size, max_pages=max_pages):
            if event["type"] == "error":
                return {"error": event["data"]}
            if event["type"] == "done":
                result = {
                    "ok": True,
                    "total": len(event["documents"]),
                    "pages": event["pages"],
                    "documents": event["documents"],
                }
        return result or {"error": "Нет данных"}

    def memos_stream(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        page_size: int = 50,
        max_pages: int = 15,
    ):
        """Генератор SSE-событий для поиска записок (reasoning + done).

        Как memos(), но отдаёт reasoning батч-LLM по мере обхода индекса
        (событие `reasoning`), а финал — `done` с документами.
        """
        if self.is_syncing:
            yield {"type": "error", "data": "Идет синхронизация"}
            return
        if not self.is_initialized or self.index is None:
            yield {"type": "error", "data": "Индекс не готов"}
            return
        if not prompt or not str(prompt).strip():
            yield {"type": "error", "data": "Поле 'prompt' обязательно"}
            return

        temperature = temperature if temperature is not None else 0.0
        page_size = max(1, int(page_size))
        max_pages = max(1, int(max_pages))

        llm = self.provider.build_llm(
            self.cfg.llm,
            self.cfg.context_window,
            temperature=temperature,
        )

        seen_ids = set()
        found_paths = []  # порядок обнаружения документов
        found_paths_set = set()
        all_sources = []
        pages_used = 0
        total_tokens_in = 0
        total_tokens_out = 0
        total_llm_time = 0.0

        # Отбор кандидатов — только семантический ретрив (по содержимому).
        # Имя файла не участвует: иначе возможны потери, если тема не
        # отражена в названии документа.
        by_path = self._index_nodes_by_path()
        seen_order = set()
        candidate_pairs = []  # [(file_path, node)] — порядок обхода батчей

        try:
            retriever = self.index.as_retriever(
                similarity_top_k=max(page_size, page_size * 3),
            )
            raw_nodes = retriever.retrieve(prompt)
        except Exception:
            raw_nodes = []
        for n in raw_nodes:
            fp = (n.node.metadata or {}).get("file_path", "")
            if not fp or fp not in by_path or n.node.node_id in seen_order:
                continue
            seen_order.add(n.node.node_id)
            candidate_pairs.append((fp, n.node))

        for page in range(max_pages):
            pages_used = page + 1

            if not candidate_pairs:
                # Кандидатов нет (пустой индекс/пустой ретрив) — завершаем.
                break
            # Постраничный проход по кандидатам (меньше контекста → короче reasoning).
            start = page * page_size
            batch_pairs = candidate_pairs[start:start + page_size]
            if not batch_pairs:
                break
            nodes = []
            for fp, nd in batch_pairs:
                if nd.node_id not in seen_ids:
                    seen_ids.add(nd.node_id)
                    nodes.append(NodeWithScore(node=nd, score=0.0))
            if not nodes:
                break

            batch_paths = set()
            context_parts = []
            for n in nodes:
                meta = n.node.metadata or {}
                fp = meta.get("file_path", "")
                if fp:
                    batch_paths.add(fp)
                    all_sources.append({
                        "file_name": meta.get("file_name", fp),
                        "file_path": fp,
                        "node_id": n.node.node_id,
                        "score": round(float(getattr(n, "score", 0.0) or 0.0), 4),
                    })
                context_parts.append(f"[Файл: {fp}]\n{n.node.get_content()}")

            sys_prompt = _MEMO_BATCH_SYSTEM_PROMPT.format(
                topic=prompt,
                page_no=page + 1,
                previously=", ".join(found_paths) if found_paths else "нет",
            )
            user_prompt = (
                sys_prompt
                + "\n\nФрагменты документов (каждый помечен строкой "
                "[Файл: <полный путь>]):\n"
                + "\n\n".join(context_parts)
            )

            # Батч-LLM стримит reasoning (thinking) + текст ответа.
            from llama_index.core.base.llms.types import ChatMessage, MessageRole
            answer_parts = []
            total_tokens_in += _count_tokens(user_prompt)
            t_batch = time.perf_counter()
            try:
                for resp in llm.stream_chat(
                    [ChatMessage(role=MessageRole.USER, content=user_prompt)]
                ):
                    token = getattr(resp, "delta", "") or ""
                    if token:
                        answer_parts.append(token)
                    thinking = (resp.additional_kwargs or {}).get("thinking_delta")
                    if thinking:
                        yield {"type": "reasoning", "data": thinking}
            except Exception as e:
                yield {"type": "error", "data": f"Ошибка LLM на батче {page + 1}: {e}"}
                return
            total_llm_time += time.perf_counter() - t_batch
            answer = "".join(answer_parts)
            total_tokens_out += _count_tokens(answer)

            added_any = False
            for m in re.finditer(r"(?:ПУТЬ:\s*)?(\S[^\n]*)", answer):
                path = m.group(1).strip()
                if path in batch_paths and path not in found_paths_set:
                    found_paths.append(path)
                    found_paths_set.add(path)
                    added_any = True

            if (not answer.strip() or "НОВЫХ ЗАПИСОК НЕТ" in answer.upper()) and not added_any:
                break

        documents = []
        nodes_by_path = self._index_nodes_by_path()
        for fp in found_paths:
            documents.append({
                "file_name": os.path.basename(fp) or fp,
                "file_path": fp,
                "text": self._assemble_document_text(fp, nodes_by_path.get(fp)),
            })

        # Суммарные метрики времени/токенов батч-LLM по всем страницам.
        yield {
            "type": "done",
            "documents": documents,
            "pages": pages_used,
            "prompt": prompt,
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "elapsed": round(total_llm_time, 2),
        }

    def _index_nodes_by_path(self) -> dict:
        """Строит file_path -> [nodes] по docstore один раз (O(N) за вызов).

        Используется для сборки полного текста множества документов:
        вместо вложенного сканирования docstore на каждый файл (O(N*M)).
        """
        if not self.index:
            return {}
        try:
            docs = self.index.docstore.docs or {}
        except Exception:
            return {}
        by_path = {}
        for n in docs.values():
            fp = (n.metadata or {}).get("file_path")
            if fp and getattr(n, "start_char_idx", None) is not None:
                by_path.setdefault(fp, []).append(n)
        for nodes in by_path.values():
            nodes.sort(key=lambda n: n.start_char_idx)
        return by_path

    def _assemble_document_text(self, file_path: str,
                                nodes: Optional[list] = None) -> Optional[str]:
        """Собирает полный текст документа из узлов docstore по file_path.

        Узлы сортируются по start_char_idx; перекрытия (chunk_overlap)
        вырезаются. Если узлов в индексе нет — возвращает None.
        Принимает готовый список узлов (из _index_nodes_by_path), иначе
        сканирует docstore (режим одного файла).
        """
        if not self.index:
            return None
        if nodes is None:
            try:
                nodes = [
                    n for n in (self.index.docstore.docs or {}).values()
                    if (n.metadata or {}).get("file_path") == file_path
                    and getattr(n, "start_char_idx", None) is not None
                ]
            except Exception:
                return None
            if not nodes:
                return None
            nodes.sort(key=lambda n: n.start_char_idx)
        if not nodes:
            return None

        full = ""
        prev_end = 0
        for n in nodes:
            start = n.start_char_idx
            text = n.text or ""
            if start >= prev_end:
                full += text
            else:
                overlap = prev_end - start
                full += text[overlap:]
            prev_end = n.end_char_idx
        return full or None

    # ------------------------------------------------------------------
    #  Статус и доступ к конфигу
    # ------------------------------------------------------------------
    def get_status(self) -> dict:
        return {
            "is_initialized": self.is_initialized,
            "is_syncing": self.is_syncing,
            "status": self.sync_status,
            "progress": self.sync_progress,
            "status_backend": self.status_backend,
            "document_count": self.get_document_count(),
            "sync_files": self.sync_file,
            "index_updated": self.get_data_bd(),
            "version": getattr(self, "version", None),
        }

    def get_document_count(self) -> int:
        return len(self.file_hash_db.get_all_paths())

    def get_data_bd(self):
        p = Path(self.cache_dir + "/faiss_index/graph_store.json")
        if p.exists():
            ts = p.stat().st_mtime
            return datetime.fromtimestamp(ts).replace(microsecond=0).isoformat()
        return "--.--.--"

    def get_config(self) -> dict:
        return self.cfg.to_dict()

    def update_config(self, **kwargs) -> dict:
        old_provider = self.cfg.provider
        changed = self.cfg.update(**kwargs)
        if "provider" in changed and "url" not in kwargs:
            # Провайдер сменился, url не трогали — подставляем адрес по умолчанию
            # только если текущий url всё ещё равен умолчанию старого провайдера.
            from .providers import DEFAULT_URLS
            if self.cfg.url == DEFAULT_URLS.get(old_provider):
                changed += self.cfg.update(url=DEFAULT_URLS.get(self.cfg.provider))
        if "chunk_size" in changed or "chunk_overlap" in changed:
            self.node_parser.chunk_size = self.cfg.chunk_size
            self.node_parser.chunk_overlap = self.cfg.chunk_overlap
        restart_index = bool({"chunk_size", "chunk_overlap", "llm_embed", "embedding_dim"} & set(changed))
        restart_llm = bool({"llm_embed", "llm", "llm_keywords"} & set(changed))
        if "provider" in changed or "url" in changed or "api_key" in changed:
            from .providers import create_provider
            self.provider = create_provider(
                self.cfg.provider, self.cfg.url, self.cfg.api_key
            )
            restart_llm = True
        if restart_llm:
            self.__init_backend()
            self.__check_backend()
            auto = self._autofix_models_for_provider(kwargs)
            if auto:
                self.__init_backend()
                changed += auto
                if {"llm_embed", "embedding_dim"} & set(auto):
                    restart_index = True
        if restart_index:
            self.start_sync(is_remove=True)
        return {"changed": changed}

    def _autofix_models_for_provider(self, kwargs: dict) -> list:
        """При смене провайдера подставляет доступные у него модели.

        Срабатывает только если бэкенд ответил и пользователь не указал модель
        явно. Вручную выбранные модели не трогаем.
        """
        if not self.status_backend or not self.backend_models:
            return []
        auto = []
        if "llm" not in kwargs and self.cfg.llm not in self.backend_models and self.backend_models_thinking:
            auto += self.cfg.update(llm=self.backend_models_thinking[0])
        if "llm_keywords" not in kwargs and self.cfg.llm_keywords not in self.backend_models and self.backend_models_thinking:
            auto += self.cfg.update(llm_keywords=self.backend_models_thinking[0])
        if "llm_embed" not in kwargs and self.cfg.llm_embed not in self.backend_models_embed and self.backend_models_embed:
            auto += self.cfg.update(llm_embed=self.backend_models_embed[0])
        return auto

    def start_sync(self, is_remove: bool = False) -> None:
        thread = threading.Thread(target=self.sync_index, args=(is_remove,), daemon=True)
        thread.start()

    def get_backend_models(self) -> dict:
        return {
            "all": self.backend_models,
            "thinking": self.backend_models_thinking,
            "embedding": self.backend_models_embed,
        }

    def refresh_backend_models(self) -> bool:
        """Повторно проверяет доступность бэкенда и обновляет списки моделей."""
        self.__check_backend()
        return self.status_backend

    def set_sync_folders(self, folders: List[str]) -> None:
        self.cfg.sync_folders = folders
        self.cfg.save()
        self.documents_paths = folders or []
