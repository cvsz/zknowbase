import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings


class ProviderError(RuntimeError):
    pass


class AIProviders:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        provider = self.settings.embedding_provider
        if provider == "ollama":
            payload = {"model": self.settings.embedding_model, "input": texts}
            data = await self._post_json(f"{self.settings.ollama_base_url}/api/embed", payload)
            return data["embeddings"]
        if provider == "openai":
            key = self._required(self.settings.openai_api_key, "OPENAI_API_KEY")
            data = await self._post_json(
                f"{self.settings.openai_base_url.rstrip('/')}/embeddings",
                {"model": self.settings.embedding_model, "input": texts},
                {"Authorization": f"Bearer {key}"},
            )
            return [item["embedding"] for item in data["data"]]
        if provider == "gemini":
            key = self._required(self.settings.gemini_api_key, "GEMINI_API_KEY")
            results: list[list[float]] = []
            for text in texts:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self.settings.embedding_model}:embedContent?key={key}"
                )
                data = await self._post_json(
                    url,
                    {"content": {"parts": [{"text": text}]}},
                )
                results.append(data["embedding"]["values"])
            return results
        raise ProviderError(f"Unknown embedding provider: {provider}")

    async def complete(self, system: str, prompt: str) -> str:
        provider = self.settings.llm_provider
        if provider == "ollama":
            data = await self._post_json(
                f"{self.settings.ollama_base_url}/api/chat",
                {
                    "model": self.settings.llm_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            return data["message"]["content"]
        if provider == "openai":
            key = self._required(self.settings.openai_api_key, "OPENAI_API_KEY")
            data = await self._post_json(
                f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
                {
                    "model": self.settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
                {"Authorization": f"Bearer {key}"},
            )
            return data["choices"][0]["message"]["content"]
        if provider == "anthropic":
            key = self._required(self.settings.anthropic_api_key, "ANTHROPIC_API_KEY")
            data = await self._post_json(
                "https://api.anthropic.com/v1/messages",
                {
                    "model": self.settings.llm_model,
                    "max_tokens": 2048,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
                {"x-api-key": key, "anthropic-version": "2023-06-01"},
            )
            return "".join(block.get("text", "") for block in data.get("content", []))
        if provider == "gemini":
            key = self._required(self.settings.gemini_api_key, "GEMINI_API_KEY")
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.settings.llm_model}:generateContent?key={key}"
            )
            data = await self._post_json(
                url,
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                },
            )
            return data["candidates"][0]["content"]["parts"][0]["text"]
        raise ProviderError(f"Unknown LLM provider: {provider}")

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        provider = self.settings.llm_provider
        if provider == "ollama":
            payload = {
                "model": self.settings.llm_model,
                "stream": True,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"{self.settings.ollama_base_url}/api/chat",
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            event = json.loads(line)
                            token = event.get("message", {}).get("content", "")
                            if token:
                                yield token
                return
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                raise ProviderError(f"Ollama streaming failed: {exc}") from exc

        if provider == "openai":
            key = self._required(self.settings.openai_api_key, "OPENAI_API_KEY")
            payload = {
                "model": self.settings.llm_model,
                "stream": True,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {key}"},
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            event = json.loads(data)
                            token = event["choices"][0].get("delta", {}).get("content", "")
                            if token:
                                yield token
                return
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
                raise ProviderError(f"OpenAI streaming failed: {exc}") from exc

        # Anthropic/Gemini retain API-compatible SSE semantics through a completion fallback.
        # Native streaming can be added without changing callers or the external endpoint.
        text = await self.complete(system, prompt)
        words = text.split(" ")
        for index, word in enumerate(words):
            yield word + (" " if index < len(words) - 1 else "")

    async def _post_json(
        self,
        url: str,
        payload: dict,
        headers: dict | None = None,
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc

    @staticmethod
    def _required(value: str | None, name: str) -> str:
        if not value:
            raise ProviderError(f"{name} is required for the selected provider")
        return value
