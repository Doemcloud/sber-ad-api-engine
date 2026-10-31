"""Живая проверка GigaChat: ключ → токен → список моделей → вызов функции.
Запуск из папки agent (переменные берутся из ../.env или окружения):
    python gigachat_check.py            # чат и вызов функции
    python gigachat_check.py --image    # плюс нейрогенерация картинки (сохранится в gigachat_check.jpg)
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

env = Path(__file__).resolve().parent.parent / ".env"
if env.exists():
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
os.environ["LLM_PROVIDER"] = "gigachat"

from app import llm  # noqa: E402

m = llm.from_env()
if not isinstance(m, llm.GigaChat):
    sys.exit("Нет ключа: задайте GIGACHAT_AUTH_KEY или GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET в .env")

print(f"1. Токен ({m.scope}) … ", end="", flush=True)
token = m._auth()
print("ok")

print("2. Адрес API … ", end="", flush=True)
base = m.pick_base()
print(base)
print("   Модели … ", end="", flush=True)
req = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
with urllib.request.urlopen(req, timeout=30, context=m.ctx) as r:
    names = [x["id"] for x in json.loads(r.read()).get("data", [])]
print(", ".join(names))
if m.model not in names:
    print(f"   ⚠ модели {m.model} нет в списке для этого ключа — задайте LLM_MODEL одной из перечисленных")

print(f"3. {m.model}: вызов функции … ", end="", flush=True)
tools = [{"name": "get_segments", "description": "Список сегментов аудитории с числом клиентов",
          "parameters": {"type": "object", "properties": {}}}]
r = m.complete([{"role": "system", "content": "Ты ассистент менеджера рекламных кампаний. Отвечай по-русски."},
                {"role": "user", "content": "Какие сегменты аудитории есть? Посмотри в справочнике."}], tools)
if r["tool_calls"]:
    print("ok, модель вызвала", r["tool_calls"][0]["name"])
else:
    print("модель ответила текстом без вызова функции:", (r["content"] or "")[:200])
if "--image" in sys.argv:
    from app.images import GigaChatImages, build_prompt  # noqa: E402
    print("4. Нейрогенерация (text2image) … ", end="", flush=True)
    data, mime = GigaChatImages(m).generate(build_prompt("Стеклянная копилка с зелёными ростками, мягкий утренний свет", "SMART_BANNER"), "SMART_BANNER")
    out = Path(__file__).resolve().parent / ("gigachat_check.jpg" if mime == "image/jpeg" else "gigachat_check.png")
    out.write_bytes(data)
    print(f"ok, {len(data) // 1024} КБ → {out.name}")
print("Готово: GigaChat подключён.")
