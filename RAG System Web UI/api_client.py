"""Обёртка над RAG System API."""
import json
import time
from typing import Iterator

import requests


class RAGClient:
    def __init__(self, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, endpoint: str, **kwargs) -> dict:
        try:
            resp = requests.get(f"{self.base_url}/{endpoint}", timeout=self.timeout, **kwargs)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        return {}

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = requests.request(method, f"{self.base_url}/{endpoint}", **kwargs)
            if resp.status_code == 200:
                return resp.json()
            return resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {"error": resp.text}
        except requests.RequestException as e:
            return {"error": str(e)}

    def health(self) -> dict:
        return self._get("health")

    def info(self) -> dict:
        return self._get("info")

    def engine_status(self) -> dict:
        return self._get("engine/status")

    def index_status(self) -> dict:
        return self._get("index/status")

    def index_stats(self) -> dict:
        return self._get("index/stats")

    def trigger_sync(self, reset: bool = False) -> dict:
        params = {"reset": "true"} if reset else {}
        return self._request("post", "index", params=params)

    # --- Расписание ограничений (источник — ядро) ---

    def get_schedule(self) -> dict:
        return self._request("get", "schedule")

    def add_schedule(self, data: dict) -> dict:
        return self._request("post", "schedule", json=data)

    def update_schedule(self, rid: int, data: dict) -> dict:
        return self._request("put", f"schedule/{rid}", json=data)

    def delete_schedule(self, rid: int) -> dict:
        return self._request("delete", f"schedule/{rid}")

    def get_config(self) -> dict:
        return self._get("config")

    def patch_config(self, **kwargs) -> dict:
        return self._request("patch", "config", json=kwargs)

    def reset_config(self) -> dict:
        return self._request("post", "config/reset")

    def list_models(self) -> dict:
        return self._get("models")

    def get_provider(self) -> dict:
        return self._get("provider")

    def set_provider(self, provider: str) -> dict:
        return self._request("post", "provider", json={"provider": provider})

    def get_folders(self) -> list:
        data = self._get("folders")
        return data.get("folders", [])

    def set_folders(self, folders: list) -> dict:
        return self._request("post", "folders", json={"folders": folders})

    def stream_chat(self, prompt: str, system_prompt: str = None,
                    top_k: int = None, temperature: float = 0.98,
                    exclude_node_ids: list = None) -> Iterator[dict]:
        payload = {"prompt": prompt, "temperature": temperature}
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if top_k is not None:
            payload["top_k"] = top_k
        if exclude_node_ids:
            payload["exclude_node_ids"] = list(exclude_node_ids)

        try:
            resp = requests.post(
                f"{self.base_url}/agent/stream",
                json=payload, stream=True, timeout=(10, 600),
            )
            if resp.status_code >= 400:
                try:
                    err = resp.json()
                    yield {"type": "error", "data": err.get("error", f"HTTP {resp.status_code}")}
                except Exception:
                    yield {"type": "error", "data": f"HTTP {resp.status_code}"}
                return

            buffer = b""
            for chunk in resp.iter_content(chunk_size=4096):
                buffer += chunk
                while b"\n\n" in buffer:
                    line, buffer = buffer.split(b"\n\n", 1)
                    yield self._parse_sse_line(line)
            if buffer.strip():
                yield self._parse_sse_line(buffer)
        except requests.RequestException as e:
            yield {"type": "error", "data": str(e)}

    @staticmethod
    def _parse_sse_line(line: bytes) -> dict:
        data_str = line.decode("utf-8", errors="replace").strip()
        if data_str.startswith("data: "):
            try:
                return json.loads(data_str[6:])
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def parse_file(self, file_path: str) -> dict:
        return self._request("post", "parse", json={"file_path": file_path})

    def memos(self, prompt: str, temperature: float = 0.2,
              page_size: int = 50, max_pages: int = 15) -> dict:
        """Поиск всех записок по теме (ядро отдаёт полный текст документов)."""
        return self._request(
            "post",
            "memos",
            json={
                "prompt": prompt,
                "temperature": temperature,
                "page_size": page_size,
                "max_pages": max_pages,
            },
            timeout=900,
        )

    def memos_stream(self, prompt: str, temperature: float = 0.2,
                     page_size: int = 50, max_pages: int = 15) -> Iterator[dict]:
        """Поиск записок по теме с потоковым reasoning (SSE).

        События: reasoning / done (documents) / error.
        """
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "page_size": page_size,
            "max_pages": max_pages,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/memos/stream",
                json=payload, stream=True, timeout=(10, 900),
            )
            if resp.status_code >= 400:
                try:
                    err = resp.json()
                    yield {"type": "error", "data": err.get("error", f"HTTP {resp.status_code}")}
                except Exception:
                    yield {"type": "error", "data": f"HTTP {resp.status_code}"}
                return

            buffer = b""
            for chunk in resp.iter_content(chunk_size=4096):
                buffer += chunk
                while b"\n\n" in buffer:
                    line, buffer = buffer.split(b"\n\n", 1)
                    yield self._parse_sse_line(line)
            if buffer.strip():
                yield self._parse_sse_line(buffer)
        except requests.RequestException as e:
            yield {"type": "error", "data": str(e)}

    def parse_file_stream(self, file_path: str) -> Iterator[dict]:
        try:
            resp = requests.post(
                f"{self.base_url}/parse/stream",
                json={"file_path": file_path}, stream=True, timeout=(10, 600),
            )
            buffer = b""
            for chunk in resp.iter_content(chunk_size=4096):
                buffer += chunk
                while b"\n\n" in buffer:
                    line, buffer = buffer.split(b"\n\n", 1)
                    yield self._parse_sse_line(line)
            if buffer.strip():
                yield self._parse_sse_line(buffer)
        except requests.RequestException as e:
            yield {"type": "error", "data": str(e)}
