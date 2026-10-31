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
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Protocol


class LLMUnavailable(RuntimeError):
    """Модель временно недоступна (лимиты, сеть). Агент отвечает человеку, а не падает."""


class LLM(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


def _http(url: str, method: str, body: dict | str | None, headers: dict, ctx: ssl.SSLContext | None = None, timeout: float = 120) -> bytes:
    data = None if body is None else body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def _post(url: str, body: dict | str, headers: dict, ctx: ssl.SSLContext | None = None, timeout: float = 120) -> dict:
    return json.loads(_http(url, "POST", body, headers, ctx, timeout))


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
    """Нативный API GigaChat (developers.sber.ru/docs/ru/gigachat).

    Авторизация: OAuth-токен по ключу авторизации (Basic = base64 «client_id:client_secret»),
    токен живёт ~30 минут и обновляется сам. Вызов инструментов — через functions /
    function_call (GigaChat вызывает одну функцию за сообщение, агент крутит цикл).

    Физлицам (в т.ч. Freemium) GigaChat даёт ОДИН поток: параллельный запрос получает 429.
    Поэтому все запросы процесса идут строго по очереди через общий замок, а 429/5xx
    повторяются с растущей паузой.

    Переменные окружения:
      GIGACHAT_AUTH_KEY      — ключ авторизации из кабинета; или пара
      GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET — ключ соберётся сам;
      GIGACHAT_SCOPE         — GIGACHAT_API_PERS | GIGACHAT_API_B2B | GIGACHAT_API_CORP;
      LLM_MODEL              — по умолчанию GigaChat-3-Ultra;
      GIGACHAT_BASE_URL      — адрес API или несколько через запятую; по умолчанию пробуется
                               https://api.giga.chat/v1 (единый адрес с 16.07.2026), затем
                               https://gigachat.devices.sberbank.ru/api/v1 — берётся первый доступный;
      GIGACHAT_OAUTH_URL     — по умолчанию https://ngw.devices.sberbank.ru:9443/api/v2/oauth;
      GIGACHAT_CA_BUNDLE     — путь к сертификату «Russian Trusted Root CA» (Минцифры);
      GIGACHAT_VERIFY_SSL=0  — отключить проверку сертификата (только для демо);
      GIGACHAT_MAX_RETRIES   — повторов при 429/5xx/сбое сети (по умолчанию 5, паузы 2→4→8→16→30 с);
      GIGACHAT_MIN_INTERVAL  — минимальная пауза между запросами, с (по умолчанию 0.3)."""

    _lock = threading.Lock()  # один поток на весь процесс агента
    _last = 0.0

    def __init__(self):
        self.auth_key = gigachat_auth_key()
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.model = os.getenv("LLM_MODEL") or "GigaChat-3-Ultra"
        self.oauth_url = os.getenv("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        urls = os.getenv("GIGACHAT_BASE_URL") or "https://api.giga.chat/v1,https://gigachat.devices.sberbank.ru/api/v1"
        self.bases = [u.strip().rstrip("/") for u in urls.split(",") if u.strip()]
        self.base = self.bases[0] if len(self.bases) == 1 else ""
        ca = os.getenv("GIGACHAT_CA_BUNDLE")
        self.ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
        if os.getenv("GIGACHAT_VERIFY_SSL", "1") == "0":
            self.ctx.check_hostname, self.ctx.verify_mode = False, ssl.CERT_NONE
        self._token, self._exp = "", 0.0

    def _auth(self, force: bool = False) -> str:
        if self._token and not force and time.time() < self._exp - 60:
            return self._token
        r = _post(self.oauth_url, f"scope={self.scope}", {
            "Authorization": f"Basic {self.auth_key}", "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, self.ctx)
        exp = float(r.get("expires_at") or 0)
        self._token = r["access_token"]
        self._exp = exp / 1000 if exp > 1e11 else (exp or time.time() + 1500)  # expires_at — в миллисекундах
        return self._token

    def pick_base(self) -> str:
        """Первый адрес API, до которого есть соединение (GET /models, короткий таймаут)."""
        if self.base:
            return self.base
        errors = []
        for b in self.bases:
            try:
                req = urllib.request.Request(f"{b}/models", headers={"Authorization": f"Bearer {self._auth()}", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=float(os.getenv("GIGACHAT_PROBE_TIMEOUT", "8")), context=self.ctx):
                    pass
                self.base = b
                return b
            except urllib.error.HTTPError as e:
                if e.code < 500:  # сервер ответил — адрес рабочий
                    self.base = b
                    return b
                errors.append(f"{b}: HTTP {e.code}")
            except OSError as e:
                errors.append(f"{b}: {getattr(e, 'reason', e)}")
        raise LLMUnavailable("GigaChat недоступен ни по одному адресу: " + "; ".join(errors))

    @staticmethod
    def _json_object(text: str) -> str:
        """Результат функции GigaChat принимает только как JSON-объект в строке."""
        try:
            v = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"result": text}, ensure_ascii=False)
        return text if isinstance(v, dict) else json.dumps({"result": v}, ensure_ascii=False)

    def _messages(self, messages: list[dict]) -> list[dict]:
        msgs = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                c = m["tool_calls"][0]  # GigaChat вызывает одну функцию за сообщение
                a = {"role": "assistant", "content": m.get("content") or "",
                     "function_call": {"name": c["name"], "arguments": c["arguments"]}}
                if c.get("state_id"):
                    a["functions_state_id"] = c["state_id"]
                msgs.append(a)
            elif m["role"] == "tool":
                msgs.append({"role": "function", "name": m.get("name", ""), "content": self._json_object(m["content"])})
            else:
                msgs.append({"role": m["role"], "content": m["content"] or ""})
        return msgs

    def _send(self, body: dict | None, path: str = "/chat/completions", method: str = "POST", accept: str = "application/json"):
        """Запрос к API GigaChat с повторами; JSON-ответ — словарь, иначе — байты (файлы)."""
        retries = int(os.getenv("GIGACHAT_MAX_RETRIES", "5"))
        gap = float(os.getenv("GIGACHAT_MIN_INTERVAL", "0.3"))
        refreshed = False
        attempt = 0
        while True:
            wait = gap - (time.time() - GigaChat._last)
            if wait > 0:
                time.sleep(wait)
            try:
                hdr = {"Accept": accept, "Authorization": f"Bearer {self._auth()}"}
                if body is not None:
                    hdr["Content-Type"] = "application/json"
                raw = _http(f"{self.pick_base()}{path}", method, body, hdr, self.ctx)
                return json.loads(raw) if accept == "application/json" else raw
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:500]
                if e.code == 401 and not refreshed:  # токен истёк — обновить и повторить
                    self._auth(force=True)
                    refreshed = True
                    continue
                if e.code != 429 and e.code < 500:
                    raise RuntimeError(f"GigaChat {e.code}: {text}") from e
                if attempt >= retries:
                    raise LLMUnavailable(f"GigaChat {e.code}: {text}") from e
                ra = e.headers.get("Retry-After") if e.headers else None
                delay = float(ra) if ra and ra.replace(".", "", 1).isdigit() else min(2 ** (attempt + 1), 30)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt >= retries:
                    raise LLMUnavailable(f"GigaChat недоступен: {getattr(e, 'reason', e)}") from e
                delay = min(2 ** (attempt + 1), 30)
            finally:
                GigaChat._last = time.time()
            attempt += 1
            time.sleep(delay)

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        body = {"model": self.model, "messages": self._messages(messages), "temperature": 0.2, "function_call": "auto",
                "functions": [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in tools]}
        with GigaChat._lock:
            r = self._send(body)
        msg = r["choices"][0]["message"]
        fc = msg.get("function_call")
        calls = []
        if fc:
            args = fc.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "name": fc["name"], "arguments": args,
                          "state_id": msg.get("functions_state_id")})
        return {"content": msg.get("content"), "tool_calls": calls}


def gigachat_auth_key() -> str:
    key = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
    cid, sec = os.getenv("GIGACHAT_CLIENT_ID", "").strip(), os.getenv("GIGACHAT_CLIENT_SECRET", "").strip()
    return key or (basic_key(cid, sec) if cid and sec else "")


class NotConfigured:
    """Без ключа: агент отвечает подсказкой, остальная система работает (фронт, API, подтверждения)."""

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        return {"content": "LLM не настроена: задайте LLM_PROVIDER и ключ в .env (см. .env.example). "
                           "API кампаний, справочники и превью работают и без модели.", "tool_calls": []}


def from_env() -> LLM:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "gigachat":
        return GigaChat() if gigachat_auth_key() else NotConfigured()
    return OpenAICompatible() if os.getenv("LLM_API_KEY") else NotConfigured()


def basic_key(client_id: str, secret: str) -> str:
    """Помощник: собрать GIGACHAT_AUTH_KEY из Client ID и Client Secret."""
    return base64.b64encode(f"{client_id}:{secret}".encode()).decode()
