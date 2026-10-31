"""Слой абстракции LLM (task.md §10.8): логика агента не зависит от модели.
Нейтральный формат сообщений:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [{"id", "name", "arguments": dict}], "tool_call_id", "name"}
Ответ модели: {"content": str|None, "tool_calls": [...]}.

Провайдеры: openai (любой OpenAI-совместимый API: OpenAI, OpenRouter, vLLM,
Ollama, прокси к GigaChat) и gigachat (нативный REST API GigaChat).
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.request
import uuid
from typing import Protocol


class LLM(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


def _post(url: str, body: dict | str, headers: dict, ctx: ssl.SSLContext | None = None, timeout: float = 120) -> dict:
    data = body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read())


class OpenAICompatible:
    def __init__(self):
        self.base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        msgs = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                    for c in m["tool_calls"]]})
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        body = {"model": self.model, "messages": msgs, "temperature": 0.2,
                "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]}
        r = _post(f"{self.base}/chat/completions", body, {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        msg = r["choices"][0]["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": c["function"].get("arguments")}
            calls.append({"id": c["id"], "name": c["function"]["name"], "arguments": args})
        return {"content": msg.get("content"), "tool_calls": calls}


class GigaChat:
    """Нативный API GigaChat: OAuth-токен + /chat/completions с functions.
    GIGACHAT_AUTH_KEY — ключ авторизации (Basic) из личного кабинета;
    GIGACHAT_SCOPE — GIGACHAT_API_PERS | GIGACHAT_API_B2B | GIGACHAT_API_CORP;
    GIGACHAT_CA_BUNDLE — путь к сертификату НУЦ Минцифры (или GIGACHAT_VERIFY_SSL=0 на демо)."""

    def __init__(self):
        self.auth_key = os.getenv("GIGACHAT_AUTH_KEY", "")
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.model = os.getenv("LLM_MODEL", "GigaChat-2-Max")
        self.oauth_url = os.getenv("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        self.base = os.getenv("GIGACHAT_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1").rstrip("/")
        ca = os.getenv("GIGACHAT_CA_BUNDLE")
        self.ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
        if os.getenv("GIGACHAT_VERIFY_SSL", "1") == "0":
            self.ctx.check_hostname, self.ctx.verify_mode = False, ssl.CERT_NONE
        self._token, self._exp = "", 0.0

    def _auth(self) -> str:
        if self._token and time.time() < self._exp - 60:
            return self._token
        r = _post(self.oauth_url, f"scope={self.scope}", {
            "Authorization": f"Basic {self.auth_key}", "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, self.ctx)
        self._token, self._exp = r["access_token"], r.get("expires_at", 0) / 1000
        return self._token

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        msgs = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                c = m["tool_calls"][0]  # GigaChat вызывает одну функцию за сообщение
                msgs.append({"role": "assistant", "content": m.get("content") or "", "function_call": {"name": c["name"], "arguments": c["arguments"]}})
            elif m["role"] == "tool":
                msgs.append({"role": "function", "name": m.get("name", ""), "content": m["content"]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        body = {"model": self.model, "messages": msgs, "temperature": 0.2, "function_call": "auto",
                "functions": [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in tools]}
        r = _post(f"{self.base}/chat/completions", body, {
            "Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {self._auth()}"}, self.ctx)
        msg = r["choices"][0]["message"]
        fc = msg.get("function_call")
        calls = []
        if fc:
            args = fc.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "name": fc["name"], "arguments": args})
        return {"content": msg.get("content"), "tool_calls": calls}


class NotConfigured:
    """Без ключа: агент отвечает подсказкой, остальная система работает (фронт, API, подтверждения)."""

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        return {"content": "LLM не настроена: задайте LLM_PROVIDER и ключ в .env (см. .env.example). "
                           "API кампаний, справочники и превью работают и без модели.", "tool_calls": []}


def from_env() -> LLM:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "gigachat":
        return GigaChat() if os.getenv("GIGACHAT_AUTH_KEY") else NotConfigured()
    return OpenAICompatible() if os.getenv("LLM_API_KEY") else NotConfigured()


def basic_key(client_id: str, secret: str) -> str:
    """Помощник: собрать GIGACHAT_AUTH_KEY из Client ID и Client Secret."""
    return base64.b64encode(f"{client_id}:{secret}".encode()).decode()
