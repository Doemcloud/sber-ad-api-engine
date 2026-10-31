"""Креативы: картинка (через image API или SVG-заглушка) и автопроверка
по лимитам места показа и запрещённым формулировкам."""
import base64
import html
import os

import httpx

IMAGE_API_URL = os.getenv("IMAGE_API_URL")  # OpenAI-совместимый /v1/images/generations
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "")

FORBIDDEN = ["гарантированный доход", "без отказа", "100% одобрение", "лучший банк", "бесплатно навсегда"]


def make_image(prompt: str, title: str, size: str | None) -> str:
    if IMAGE_API_URL and IMAGE_API_KEY:
        try:
            r = httpx.post(
                IMAGE_API_URL,
                headers={"Authorization": f"Bearer {IMAGE_API_KEY}"},
                json={"model": IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "response_format": "b64_json"},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()["data"][0]
            return data.get("url") or "data:image/png;base64," + data["b64_json"]
        except Exception:  # демо не должно падать из-за генератора картинок
            pass
    return placeholder(title, size)


def placeholder(title: str, size: str | None) -> str:
    w, h = (int(x) for x in (size or "343x180").split("x"))
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>
<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#21A038'/><stop offset='1' stop-color='#0B7A3E'/></linearGradient></defs>
<rect width='100%' height='100%' rx='16' fill='url(#g)'/>
<text x='50%' y='50%' fill='white' font-family='sans-serif' font-size='{max(14, h // 8)}' text-anchor='middle' dominant-baseline='middle'>{html.escape(title[:40])}</text></svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def check(creative: dict, placement: dict | None) -> list[str]:
    issues = []
    limits = (placement or {}).get("limits", {})
    for field in ("title", "text", "button"):
        lim = limits.get(field)
        val = creative.get(field) or ""
        if lim and len(val) > lim:
            issues.append(f"{field}: {len(val)} символов при лимите {lim}")
    if placement and creative.get("type") not in placement.get("creative_types", []):
        issues.append(f"тип {creative.get('type')} не подходит для места {placement['id']}")
    text = " ".join(str(creative.get(f, "")) for f in ("title", "text", "button")).lower()
    for w in FORBIDDEN:
        if w in text:
            issues.append(f"запрещённая формулировка: «{w}»")
    if not creative.get("title"):
        issues.append("нет заголовка")
    return issues
