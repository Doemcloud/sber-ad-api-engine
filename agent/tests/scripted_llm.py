"""Скриптованная «модель» для воспроизводимых диалогов и тестов: вместо LLM
отдаёт заранее заданные ответы. Логика агента (план, проверки, подтверждение,
выполнение, перевод ошибок) при этом работает настоящая — против настоящего API."""
from __future__ import annotations

import itertools

_ids = itertools.count(1)


def call(_tool: str, **args) -> dict:
    return {"id": f"call_{next(_ids)}", "name": _tool, "arguments": args}


def calls(*cs) -> dict:
    return {"content": "", "tool_calls": list(cs)}


def say(text: str) -> dict:
    return {"content": text, "tool_calls": []}


class ScriptedLLM:
    """responses: список ответов; элемент может быть функцией (messages) -> ответ,
    чтобы подставить id, известные только после выполнения."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools):
        self.seen.append(messages)
        if not self.responses:
            return say("(скрипт закончился)")
        r = self.responses.pop(0)
        return r(messages) if callable(r) else r

    def last_tool_results(self) -> list[dict]:
        import json
        msgs = self.seen[-1] if self.seen else []
        return [json.loads(m["content"]) for m in msgs if m["role"] == "tool"]
