"""Служебный блок отказов: стоп-темы рекламы по законодательству РФ (prompts/compliance.json).

Работает в коде, а не только в промпте, — модель нельзя «уговорить»:
  * сообщение менеджера со стоп-темой получает отказ до обращения к модели;
  * тексты креативов и шапки кампании проверяются до постановки шага в план.
Правила лежат на сервере агента и во фронт не отдаются."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "compliance.json"
_WORD = r"(?<![0-9a-zа-яё])"  # начало слова: «вооружиться» не совпадёт с «оружие»


@lru_cache(maxsize=1)
def _rules() -> dict:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    def compile_(rs):
        return [{**r, "rx": re.compile(_WORD + "(?:" + "|".join(r["patterns"]) + ")", re.IGNORECASE)} for r in rs]

    return {"reply": data["reply"], "rules": compile_(data["rules"]), "creative": compile_(data.get("creative_only", []))}


def _norm(text: str) -> str:
    return (text or "").lower()


def check_message(text: str) -> dict | None:
    """Стоп-тема в сообщении менеджера → {id, reply}; иначе None."""
    t = _norm(text)
    for r in _rules()["rules"]:
        if r["rx"].search(t):
            return {"id": r["id"], "reply": _rules()["reply"].format(what=r["what"], law=r["law"])}
    return None


def _texts(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [x for k, val in v.items() if k not in ("url", "link", "iOS", "android", "web", "actionType", "role", "format") for x in _texts(val)]
    if isinstance(v, list):
        return [x for val in v for x in _texts(val)]
    return []


def check_creative(args: dict) -> list[dict]:
    """Ошибки для текстов баннера / промо-экрана / шапки кампании (в формате ошибок API)."""
    t = _norm(" \n ".join(_texts(args)))
    out = []
    for r in _rules()["rules"] + _rules()["creative"]:
        m = r["rx"].search(t)
        if m:
            msg = f"Текст нарушает законодательство о рекламе: {r['what']} ({r['law']})."
            out.append({"code": "AD_LAW_VIOLATION", "field": "content", "message": msg,
                        "hint": r.get("hint") or "Такую рекламу банк размещать не может — откажитесь от этой темы или замените текст."})
    return out
