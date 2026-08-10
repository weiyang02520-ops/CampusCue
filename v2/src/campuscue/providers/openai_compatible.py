"""OpenAI-compatible provider (M2a). httpx only, no vendor SDK.

- normalized endpoint: base_url + /chat/completions (no duplicate slash)
- Authorization: Bearer <secret> when secret_reference resolves; omitted otherwise
- structured output: response_format json_schema when response_schema given
- request timeout: LLMRequest.timeout_s overrides provider default when set (M2a.1-B)
- HTTP status classified BEFORE body parsing (M2a.1-17): non-JSON 401/429/5xx
  still map to correct categories
- strict success parsing: missing content is MALFORMED_OUTPUT (M2a.1-16)
- error taxonomy per errors.py; never logs request/response/Authorization
- test injection via httpx.AsyncClient/transport
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urljoin

import httpx

from campuscue.providers.base import BaseProvider
from campuscue.providers.errors import ProviderError, ProviderErrorCode
from campuscue.providers.models import LLMMessage, LLMRequest, LLMResponse
from campuscue.providers.validation import (
    validate_provider_config_numeric,
    validate_request_override,
    validate_secret_reference,
)

logger = logging.getLogger("campuscue.providers.openai_compatible")


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
        # M2a.2: constructor defense-in-depth uses the SAME canonical rules
        validate_provider_config_numeric(
            timeout_s=timeout_s, max_tokens=max_tokens,
            max_context_tokens=max_context_tokens, temperature=temperature,
        )
        validate_secret_reference(secret_reference)
        self._base_url = base_url.rstrip("/") + "/"
        self._model = model
        self._secret_reference = secret_reference
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_context_tokens = max_context_tokens
        self._timeout_s = timeout_s
        self._client = client  # injectable for tests (httpx.MockTransport)

    @property
    def model(self) -> str:
        """Configured model identifier (M2b.1.1 abstraction contract)."""
        return self._model

    @property
    def endpoint(self) -> str:
        return urljoin(self._base_url, "chat/completions")

    def _resolve_secret(self) -> str:
        """Runtime secret resolution; canonical rule in validation.py.

        M2b.1.1 (Real-Gate): secret_reference configured but referenced env
        missing/empty -> ProviderError CONFIG_ERROR, ZERO transport calls.
        Never silently send an unauthenticated HTTP request, never print the
        secret value, never let this turn into a remote 401.
        """
        if not self._secret_reference:
            return ""
        try:
            validate_secret_reference(self._secret_reference)
        except ValueError as e:
            raise ProviderError(ProviderErrorCode.CONFIG_ERROR, str(e)) from None
        value = os.environ.get(self._secret_reference)
        if value is None or value == "":
            raise ProviderError(
                ProviderErrorCode.CONFIG_ERROR,
                f"secret_reference env {self._secret_reference} is missing/empty; "
                "refusing to call the provider without authentication",
            ) from None
        return value

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
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        secret = self._resolve_secret()
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _effective_timeout(self, request: LLMRequest) -> float:
        """M2a.1-B: request-level timeout overrides provider default when set.
        (request.timeout_s already validated by chat() before transport.)"""
        if request.timeout_s is not None:
            return request.timeout_s
        return self._timeout_s

    async def _post(self, payload: dict[str, Any], headers: dict[str, str], timeout_s: float) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(self.endpoint, json=payload, headers=headers, timeout=timeout_s)
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            return await c.post(self.endpoint, json=payload, headers=headers)

    async def chat(self, request: LLMRequest) -> LLMResponse:
        # M2a.2-C: validate request overrides BEFORE any transport call
        try:
            validate_request_override(
                timeout_s=request.timeout_s,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except ValueError as e:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, str(e)) from None
        payload = self._build_payload(request)
        headers = self._headers()
        timeout_s = self._effective_timeout(request)
        try:
            resp = await self._post(payload, headers, timeout_s)
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "provider request timed out") from None
        except httpx.TransportError:
            raise ProviderError(ProviderErrorCode.NETWORK, "provider connection failed") from None

        # M2a.1-17: classify by STATUS FIRST, independent of body content.
        if resp.status_code == 401 or resp.status_code == 403:
            raise ProviderError(
                ProviderErrorCode.AUTH_ERROR, "provider authentication failed", status_code=resp.status_code
            )
        if resp.status_code == 429:
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "provider rate limited", status_code=429)
        if resp.status_code >= 500:
            raise ProviderError(ProviderErrorCode.SERVER_ERROR, "provider server error", status_code=resp.status_code)

        if resp.status_code == 400:
            raise self._classify_400(resp)
        if resp.status_code != 200:
            raise ProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                f"provider returned status {resp.status_code}",
                status_code=resp.status_code,
            )

        # 200: body must be JSON (M2a.1-17)
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.MALFORMED_OUTPUT,
                f"provider returned non-JSON response (status {resp.status_code})",
            ) from None
        return self._parse_ok(data)

    def _classify_400(self, resp: httpx.Response) -> ProviderError:
        """400: safe JSON parse only for finer classification; non-JSON -> INVALID_REQUEST.

        M2b.1.1 (Finding D): generic evidence of structured-output incompatibility
        is classified STRUCTURED_OUTPUT_UNSUPPORTED (the ONLY invalid-request
        category that permits one schema fallback). HTTP structured error fields
        (error.message / error.code / error.type) are used — no vendor-specific
        string matching, no guessing at one real vendor's wire format.
        """
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            return ProviderError(ProviderErrorCode.INVALID_REQUEST, "provider rejected request (non-JSON)", status_code=400)
        err = data.get("error") or {}
        err_type = str(err.get("type", "")).lower() if isinstance(err, dict) else ""
        err_code = str(err.get("code", "")).lower() if isinstance(err, dict) else ""
        message = str(err.get("message", "")).lower() if isinstance(err, dict) else str(err).lower()
        if any(k in message for k in ("context length", "context_length", "maximum context", "token limit", "too many tokens")):
            return ProviderError(ProviderErrorCode.CONTEXT_OVERFLOW, "context length exceeded", status_code=400)
        # structured-output / json_schema evidence FIRST (explicit error fields OR
        # message), so "invalid json_schema for model X" is not misclassified as
        # INVALID_MODEL and still gets its exactly-once schema fallback:
        if any(k in err_type for k in ("invalid_json_schema", "json_schema", "response_format", "structured_output")) or \
           any(k in err_code for k in ("invalid_json_schema", "json_schema", "response_format", "structured_output", "unsupported")) or \
           any(k in message for k in ("json_schema", "response_format", "structured_output", "structured output")):
            return ProviderError(
                ProviderErrorCode.STRUCTURED_OUTPUT_UNSUPPORTED,
                "endpoint rejected structured output (json_schema)", status_code=400,
            )
        if any(k in message for k in ("model", "not found", "does not exist", "unknown model")):
            return ProviderError(ProviderErrorCode.INVALID_MODEL, "invalid or unknown model", status_code=400)
        return ProviderError(ProviderErrorCode.INVALID_REQUEST, "provider rejected request", status_code=400)

    def _parse_ok(self, data: dict[str, Any]) -> LLMResponse:
        """M2a.1-16 STRICT success parsing: content presence is mandatory."""
        try:
            choices = data["choices"]
            if not choices or not isinstance(choices, list):
                raise KeyError("empty choices")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise KeyError("missing message dict")
            content = message.get("content")
            if not isinstance(content, str):
                raise KeyError("missing string content")
            role = message.get("role") or "assistant"
            usage = data.get("usage") or {}
        except (KeyError, IndexError, TypeError):
            raise ProviderError(
                ProviderErrorCode.MALFORMED_OUTPUT, "provider response missing choices/content"
            ) from None
        return LLMResponse(role=role, content=content, usage=usage, raw=data)

    async def test(self) -> dict:
        """Real connectivity test path: chat -> transport -> parse -> safe result."""
        resp = await self.chat(
            LLMRequest(
                messages=[LLMMessage(role="user", content="Reply PONG only")],
                model=self._model,
                max_tokens=5,
                timeout_s=min(self._timeout_s, 30.0),
            )
        )
        return {"ok": True, "model": self._model, "reply": resp.content[:20]}

