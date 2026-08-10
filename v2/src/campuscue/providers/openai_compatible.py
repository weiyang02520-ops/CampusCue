"""OpenAI-compatible provider (M2a). httpx only, no vendor SDK.

- normalized endpoint: base_url + /chat/completions (no duplicate slash)
- Authorization: Bearer <secret> when secret_reference resolves; omitted otherwise
- structured output: response_format json_schema when response_schema given
- error taxonomy per errors.py; never logs request/response/Authorization
- test injection via httpx.AsyncClient/transport
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from campuscue.providers.base import BaseProvider
from campuscue.providers.errors import ProviderError, ProviderErrorCode
from campuscue.providers.models import LLMRequest, LLMResponse

logger = logging.getLogger("campuscue.providers.openai_compatible")

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class OpenAICompatibleProvider(BaseProvider):
    provider_type = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        secret_reference: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_context_tokens: int | None = None,
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._model = model
        self._secret_reference = secret_reference
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_context_tokens = max_context_tokens
        self._timeout_s = timeout_s
        self._client = client  # injectable for tests (httpx.MockTransport)

    @property
    def endpoint(self) -> str:
        return urljoin(self._base_url, "chat/completions")

    def _resolve_secret(self) -> str | None:
        if not self._secret_reference:
            return None
        if not _ENV_NAME_RE.match(self._secret_reference):
            raise ProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                f"invalid secret_reference format: {self._secret_reference!r}",
            )
        return os.environ.get(self._secret_reference)

    def _build_payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.temperature is not None or self._temperature is not None:
            payload["temperature"] = request.temperature if request.temperature is not None else self._temperature
        if request.max_tokens is not None or self._max_tokens is not None:
            payload["max_tokens"] = request.max_tokens if request.max_tokens is not None else self._max_tokens
        if request.response_schema is not None:
            # M2 structured output contract (§38): JSON Schema reaches response_format
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        # disable_thinking: M2 §33 — provider-neutral intent; we do NOT emit an
        # invented vendor field unless a documented capability mapping exists.
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        secret = self._resolve_secret()
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    async def _post(self, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        client = self._client
        if client is None:
            async with httpx.AsyncClient(timeout=self._timeout_s) as c:
                return await c.post(self.endpoint, json=payload, headers=headers)
        return await client.post(self.endpoint, json=payload, headers=headers)

    async def chat(self, request: LLMRequest) -> LLMResponse:
        payload = self._build_payload(request)
        headers = self._headers()
        try:
            resp = await self._post(payload, headers)
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "provider request timed out") from None
        except httpx.TransportError:
            raise ProviderError(ProviderErrorCode.NETWORK, "provider connection failed") from None
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.MALFORMED_OUTPUT,
                f"provider returned non-JSON response (status {resp.status_code})",
            ) from None
        if resp.status_code >= 500:
            raise ProviderError(
                ProviderErrorCode.SERVER_ERROR, "provider server error", status_code=resp.status_code
            )
        if resp.status_code == 401 or resp.status_code == 403:
            raise ProviderError(
                ProviderErrorCode.AUTH_ERROR,
                "provider authentication failed",
                status_code=resp.status_code,
            )
        if resp.status_code == 429:
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "provider rate limited", status_code=429)
        if resp.status_code == 400:
            raise self._classify_400(data, resp.status_code)
        if resp.status_code != 200:
            raise ProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                f"provider returned status {resp.status_code}",
                status_code=resp.status_code,
            )
        return self._parse_ok(data)

    def _classify_400(self, data: dict[str, Any], status: int) -> ProviderError:
        err = data.get("error") or {}
        message = str(err.get("message", "")).lower() if isinstance(err, dict) else str(err).lower()
        if any(k in message for k in ("context length", "context_length", "maximum context", "token limit", "too many tokens")):
            return ProviderError(ProviderErrorCode.CONTEXT_OVERFLOW, "context length exceeded", status_code=status)
        if any(k in message for k in ("model", "not found", "does not exist", "unknown model")):
            return ProviderError(ProviderErrorCode.INVALID_MODEL, "invalid or unknown model", status_code=status)
        return ProviderError(ProviderErrorCode.INVALID_REQUEST, "provider rejected request", status_code=status)

    def _parse_ok(self, data: dict[str, Any]) -> LLMResponse:
        try:
            choice = data["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            role = message.get("role") or "assistant"
            usage = data.get("usage") or {}
        except (KeyError, IndexError, TypeError):
            raise ProviderError(
                ProviderErrorCode.MALFORMED_OUTPUT, "provider response missing choices/content"
            ) from None
        return LLMResponse(role=role, content=content, usage=usage, raw=data)

    async def test(self) -> dict:
        resp = await self.chat(
            LLMRequest(
                messages=[LLMMessage(role="user", content="Reply PONG only")],
                model=self._model,
                max_tokens=5,
                timeout_s=min(self._timeout_s, 30.0),
            )
        )
        return {"ok": True, "model": self._model, "reply": resp.content[:20]}
