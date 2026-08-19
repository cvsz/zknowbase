"""Lightweight zknowbase client for zworkforce and other Python consumers."""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx


class ZKnowbaseError(RuntimeError):
    pass


class ZKnowbaseClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/") + "/api/v1"
        self.client = httpx.Client(
            headers={"X-API-Key": api_key}, timeout=timeout,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ZKnowbaseClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def ask(self, question: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._json("POST", "/query", json={"question": question, "top_k": top_k, "filters": filters, "stream": False})

    def ask_stream(self, question: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        with self.client.stream("POST", self.base_url + "/query", json={"question": question, "top_k": top_k, "filters": filters, "stream": True}) as response:
            self._raise(response)
            event = "message"
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    yield {"event": event, "data": payload}

    def search(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._json("POST", "/search", json={"query": query, "top_k": top_k, "filters": filters})["results"]

    def documents(self) -> list[dict[str, Any]]:
        return self._json("GET", "/documents")

    def ingest_file(self, path: str | Path) -> dict[str, Any]:
        file_path = Path(path)
        with file_path.open("rb") as handle:
            response = self.client.post(self.base_url + "/ingest", files={"file": (file_path.name, handle)})
        self._raise(response)
        return response.json()["document"]

    def ingest_url(self, url: str) -> dict[str, Any]:
        return self._json("POST", "/ingest/url", json={"url": url})["document"]

    def reindex(self, document_id: str) -> dict[str, Any]:
        return self._json("POST", f"/documents/{document_id}/reindex")["document"]

    def delete(self, document_id: str) -> None:
        response = self.client.delete(self.base_url + f"/documents/{document_id}")
        self._raise(response)

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, self.base_url + path, **kwargs)
        self._raise(response)
        return response.json() if response.content else None

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ZKnowbaseError(f"zknowbase HTTP {response.status_code}: {detail}")
