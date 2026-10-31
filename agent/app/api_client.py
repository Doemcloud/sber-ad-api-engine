"""HTTP-клиент API кампаний (stdlib, без зависимостей). Каждый запрос несёт
X-User / X-Role — на них бэкенд строит роли и аудит (task.md §3)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from contextvars import ContextVar

# Токен вошедшего пользователя на время обработки запроса к агенту: агент ходит в API
# строго от его имени и с его правами (роль API берёт из токена, а не из заголовков).
CURRENT_TOKEN: ContextVar[str | None] = ContextVar("current_token", default=None)


class ApiError(Exception):
    def __init__(self, status: int, errors: list[dict]):
        self.status, self.errors = status, errors
        super().__init__(f"HTTP {status}: {errors}")


class ApiClient:
    def __init__(self, base: str | None = None, timeout: float = 20):
        self.base = (base or os.getenv("API_URL", "http://localhost:8080")).rstrip("/")
        self.timeout = timeout
        # Запасной режим для фоновых вызовов без пользователя: общий ключ сервиса (необязателен).
        self.service_key = os.getenv("SERVICE_KEY", "")

    def request(self, method: str, path: str, body: dict | None = None, user: str = "", role: str = ""):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if user:
            req.add_header("X-User", user)
        if role:
            req.add_header("X-Role", role)
        token = CURRENT_TOKEN.get()
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        elif self.service_key:
            req.add_header("X-Service-Key", self.service_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                errors = json.loads(raw).get("errors", [])
            except Exception:
                errors = [{"code": "HTTP_ERROR", "message": raw.decode(errors="replace")[:300]}]
            raise ApiError(e.code, errors) from None
        except urllib.error.URLError as e:
            raise ApiError(503, [{"code": "API_UNAVAILABLE", "message": f"API кампаний недоступен: {e.reason}"}]) from None

    def upload(self, path: str, data: bytes, mime: str, user: str = "", role: str = "") -> dict:
        """Загрузить изображение (POST /media) от имени вошедшего пользователя."""
        req = urllib.request.Request(self.base + path, data=data, method="POST", headers={"Content-Type": mime})
        if user:
            req.add_header("X-User", user)
        if role:
            req.add_header("X-Role", role)
        token = CURRENT_TOKEN.get()
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        elif self.service_key:
            req.add_header("X-Service-Key", self.service_key)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                errors = json.loads(e.read()).get("errors", [])
            except Exception:
                errors = [{"code": "HTTP_ERROR", "message": f"HTTP {e.code}"}]
            raise ApiError(e.code, errors) from None
        except urllib.error.URLError as e:
            raise ApiError(503, [{"code": "API_UNAVAILABLE", "message": f"API кампаний недоступен: {e.reason}"}]) from None

    def me(self, token: str) -> dict:
        """Кто вошёл: проверка токена пользователя в API кампаний."""
        req = urllib.request.Request(self.base + "/auth/me", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())["user"]
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, [{"code": "AUTH_EXPIRED", "message": "Сессия истекла — войдите заново"}]) from None
        except urllib.error.URLError as e:
            raise ApiError(503, [{"code": "API_UNAVAILABLE", "message": f"API кампаний недоступен: {e.reason}"}]) from None

    def get(self, path: str, **kw):
        return self.request("GET", path, **kw)
