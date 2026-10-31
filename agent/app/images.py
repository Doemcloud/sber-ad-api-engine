"""Нейрогенерация изображений для креативов: картинка для баннера и PROMO-экрана.

Провайдеры (IMAGE_PROVIDER):
  gigachat — встроенная функция text2image GigaChat (Kandinsky): запрос к /chat/completions
             с function_call="auto", в ответе — <img src="{file_id}">, файл — GET /files/{id}/content;
  openai   — любой OpenAI-совместимый /images/generations (gpt-image-1, dall-e-3 и т.п.);
  demo     — офлайн-заглушка: абстрактная градиентная картинка по описанию (для тестов и показа без ключа);
  off      — генерация выключена.
По умолчанию берётся тот же провайдер, что и у LLM, если для него задан ключ.

Сгенерированное изображение агент загружает в API кампаний (POST /media) и кладёт
полученную ссылку в image.url баннера / компонент image PROMO-экрана.
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import re
import struct
import zlib
from typing import Protocol

from .llm import GigaChat, LLMUnavailable, _http, _post, gigachat_auth_key


class ImageUnavailable(RuntimeError):
    """Изображение не получилось: провайдер выключен, отказал или недоступен."""


# Формат креатива → ориентация картинки.
ASPECT = {"STORY": "9:16", "SMART_BANNER": "1:1", "PROMO": "2:1"}
ORIENT = {"9:16": "вертикальная, 9:16", "1:1": "квадратная", "2:1": "горизонтальная, 2:1"}

# Общие требования к рекламной картинке банка: текст баннера рисует приложение, поэтому
# в самой картинке не должно быть надписей; без чужих брендов и узнаваемых людей.
STYLE = ("Рекламная иллюстрация для мобильного приложения банка. Современный чистый стиль, "
         "мягкий свет, спокойный фон, один ясный главный объект, место под текст. "
         "Без текста, букв и цифр, без логотипов и водяных знаков, без узнаваемых людей и знаменитостей, "
         "без купюр и монет крупным планом.")


def build_prompt(prompt: str, fmt: str, color: str | None = None) -> str:
    aspect = ASPECT.get(fmt, "1:1")
    parts = [prompt.strip().rstrip("."), f"Композиция: {ORIENT[aspect]}."]
    if color and re.fullmatch(r"#[0-9A-Fa-f]{8}", color):
        parts.append(f"Палитра сочетается с цветом фона баннера {color[:7]}.")
    parts.append(STYLE)
    return " ".join(parts)


class ImageGen(Protocol):
    name: str

    def generate(self, prompt: str, fmt: str) -> tuple[bytes, str]: ...


def sniff(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ImageUnavailable("провайдер вернул не изображение")


class GigaChatImages:
    """text2image через GigaChat: модель сама вызывает встроенную функцию рисования."""
    name = "gigachat"

    def __init__(self, giga: GigaChat | None = None):
        self.giga = giga or GigaChat()
        self.model = os.getenv("IMAGE_MODEL") or self.giga.model

    def generate(self, prompt: str, fmt: str) -> tuple[bytes, str]:
        body = {"model": self.model, "function_call": "auto", "messages": [
            {"role": "system", "content": "Ты — художник-иллюстратор рекламных баннеров банка. Рисуй строго по описанию."},
            {"role": "user", "content": f"Нарисуй: {prompt}"}]}
        try:
            with GigaChat._lock:
                r = self.giga._send(body)
                content = r["choices"][0]["message"].get("content") or ""
                m = re.search(r'<img[^>]+src="([^"]+)"', content)
                if not m:
                    raise ImageUnavailable(f"GigaChat не нарисовал изображение: {content[:200] or 'пустой ответ'}")
                if not re.fullmatch(r"[0-9A-Za-z-]{8,64}", m.group(1)):
                    raise ImageUnavailable("GigaChat вернул неожиданный идентификатор файла")
                data = self.giga._send(None, f"/files/{m.group(1)}/content", "GET", "application/jpg")
        except LLMUnavailable as e:
            raise ImageUnavailable(str(e)) from e
        except RuntimeError as e:
            if isinstance(e, ImageUnavailable):
                raise
            raise ImageUnavailable(str(e)) from e
        return data, sniff(data)


class OpenAIImages:
    name = "openai"
    SIZES = {"gpt": {"9:16": "1024x1536", "1:1": "1024x1024", "2:1": "1536x1024"},
             "dall-e-3": {"9:16": "1024x1792", "1:1": "1024x1024", "2:1": "1792x1024"}}

    def __init__(self):
        self.base = (os.getenv("IMAGE_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.key = os.getenv("IMAGE_API_KEY") or os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("IMAGE_MODEL", "gpt-image-1")

    def generate(self, prompt: str, fmt: str) -> tuple[bytes, str]:
        aspect = ASPECT.get(fmt, "1:1")
        dalle = self.model.startswith("dall-e")
        sizes = self.SIZES["dall-e-3"] if self.model == "dall-e-3" else self.SIZES["gpt"] if not dalle else {}
        body: dict = {"model": self.model, "prompt": prompt, "n": 1, "size": sizes.get(aspect, "1024x1024")}
        if dalle:
            body["response_format"] = "b64_json"
        try:
            r = _post(f"{self.base}/images/generations", body,
                      {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"}, timeout=180)
            item = (r.get("data") or [{}])[0]
            if item.get("b64_json"):
                data = base64.b64decode(item["b64_json"])
            elif item.get("url", "").startswith("https://"):
                data = _http(item["url"], "GET", None, {}, timeout=60)
            else:
                raise ImageUnavailable("провайдер не вернул изображение")
        except OSError as e:
            raise ImageUnavailable(f"генерация изображения недоступна: {getattr(e, 'reason', e)}") from e
        return data, sniff(data)


class DemoImages:
    """Без сети и ключей: детерминированная абстрактная картинка (градиент и мягкие круги)
    в палитре по описанию. Нужна для автотестов и демо, в проде не используется."""
    name = "demo"
    SIZE = {"9:16": (270, 480), "1:1": (360, 360), "2:1": (480, 240)}
    PALETTES = [((0, 138, 69), (33, 160, 56), (190, 236, 205)), ((57, 133, 214), (33, 161, 154), (214, 236, 252)),
                ((255, 140, 66), (33, 160, 56), (255, 232, 204)), ((120, 92, 214), (57, 133, 214), (232, 224, 252))]

    def generate(self, prompt: str, fmt: str) -> tuple[bytes, str]:
        h = hashlib.sha256(prompt.encode()).digest()
        w, ht = self.SIZE[ASPECT.get(fmt, "1:1")]
        a, b, light = self.PALETTES[h[0] % len(self.PALETTES)]
        blobs = [((h[i] / 255) * w, (h[i + 1] / 255) * ht, 40 + h[i + 2] % 90) for i in range(1, 13, 3)]
        rows = bytearray()
        for y in range(ht):
            rows.append(0)
            for x in range(w):
                t = (x / w + y / ht) / 2
                px = [a[k] * (1 - t) + b[k] * t for k in range(3)]
                for bx, by, r in blobs:
                    d = math.hypot(x - bx, y - by)
                    if d < r:
                        f = (1 - d / r) ** 2 * 0.55
                        px = [px[k] * (1 - f) + light[k] * f for k in range(3)]
                rows += bytes(int(v) for v in px)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, ht, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))
        return png, "image/png"


class Off:
    name = "off"

    def generate(self, prompt: str, fmt: str) -> tuple[bytes, str]:
        raise ImageUnavailable("генерация изображений не настроена (IMAGE_PROVIDER)")


def from_env() -> ImageGen:
    p = (os.getenv("IMAGE_PROVIDER") or "").lower()
    if not p:
        llm = os.getenv("LLM_PROVIDER", "openai").lower()
        if llm == "gigachat" and gigachat_auth_key():
            p = "gigachat"
        elif llm == "openai" and (os.getenv("IMAGE_API_KEY") or os.getenv("LLM_API_KEY")):
            p = "openai"
        else:
            p = "off"
    if p == "gigachat":
        return GigaChatImages() if gigachat_auth_key() else Off()
    if p == "openai":
        return OpenAIImages()
    if p == "demo":
        return DemoImages()
    return Off()


def describe_provider(g: ImageGen) -> str:
    return {"gigachat": "GigaChat (Kandinsky)", "openai": "OpenAI-совместимый API", "demo": "демо-генератор", "off": "выключена"}.get(g.name, g.name)


__all__ = ["ImageUnavailable", "build_prompt", "from_env", "describe_provider", "DemoImages", "GigaChatImages", "OpenAIImages"]
