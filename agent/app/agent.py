"""AI-агент: tool calling поверх любой LLM с OpenAI-совместимым API.

Правила, которые держит код (а не промпт):
- «хватает ли данных» решает Go API (/api/campaigns/validate);
- запись в БД (кампания, сегмент, рекламодатель) — только через pending action,
  которое менеджер подтверждает кнопкой (/confirm).
"""
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date

from openai import OpenAI

from .backend import Backend
from .creatives import check, make_image

LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # напр. https://api.openai.com/v1 или прокси к GigaChat
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
MAX_STEPS = 8

SYSTEM_PROMPT = """Ты — ассистент менеджера банка по заведению рекламных кампаний в приложении и веб-версии банка.
Сегодня {today}.

Порядок работы:
1. Разбери запрос менеджера и сразу сохрани всё, что понял, через update_draft. Помечай источник каждого поля в field_sources: request — сказано прямо, ai — ты вывел сам.
2. Сегменты, места показа и рекламодателей бери ТОЛЬКО из справочников (get_reference). Если подходящего сегмента или рекламодателя нет — предложи создать через propose_segment / propose_advertiser. Ничего не выдумывай: адреса, цены, ИНН, скидки — только от менеджера.
3. После update_draft смотри на missing. Если поля не хватает — задай уточняющие вопросы, не больше 3 за раз, к каждому предложи вариант по умолчанию.
4. Когда missing пуст — сгенерируй креативы для каждого выбранного места через generate_creatives (2 варианта на место, соблюдай лимиты символов места). Затем вызови propose_save.
5. На вопросы о существующих кампаниях отвечай через find_campaigns.

Цели (goal): visits, clicks, calls, awareness, installs, product_sales. Даты — YYYY-MM-DD, бюджет — число в рублях.
Отвечай кратко, по-русски, без markdown-таблиц. Перед вопросами коротко скажи, что уже понял."""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_reference",
        "description": "Справочник: segments (сегменты аудитории), placements (места показа с лимитами), advertisers (рекламодатели).",
        "parameters": {"type": "object", "properties": {"kind": {"enum": ["segments", "placements", "advertisers"]}}, "required": ["kind"]}}},
    {"type": "function", "function": {
        "name": "update_draft",
        "description": "Записать поля в черновик кампании. Возвращает черновик и список недостающих полей (missing).",
        "parameters": {"type": "object", "properties": {"fields": {"type": "object", "description": "Поля кампании по схеме: name, advertiser_id, goal, object, offer, target_client, segment_ids, placement_ids, budget_rub, start_date, end_date, show_hours, frequency_cap_per_day, landing_url, metrics, control_group_pct, field_sources"}}, "required": ["fields"]}}},
    {"type": "function", "function": {
        "name": "find_campaigns",
        "description": "Найти сохранённые кампании по фильтрам.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string"}, "placement_id": {"type": "string"}, "advertiser_id": {"type": "string"},
            "segment_id": {"type": "string"}, "q": {"type": "string", "description": "часть названия"}}}}},
    {"type": "function", "function": {
        "name": "propose_segment",
        "description": "Предложить создать новый сегмент аудитории (создастся после подтверждения менеджера).",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "conditions": {"type": "object"}, "reach": {"type": "integer", "description": "оценка охвата"}}, "required": ["name", "conditions"]}}},
    {"type": "function", "function": {
        "name": "propose_advertiser",
        "description": "Предложить создать карточку рекламодателя (после подтверждения менеджера).",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "inn": {"type": "string"}, "category": {"type": "string"}, "locations": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "inn", "category"]}}},
    {"type": "function", "function": {
        "name": "generate_creatives",
        "description": "Создать креативы для мест показа черновика. Картинка генерируется по image_prompt.",
        "parameters": {"type": "object", "properties": {"creatives": {"type": "array", "items": {"type": "object", "properties": {
            "placement_id": {"type": "string"}, "type": {"enum": ["smart_banner", "feed_banner", "promo_banner", "stories", "push"]},
            "variant": {"type": "string"}, "title": {"type": "string"}, "text": {"type": "string"}, "button": {"type": "string"},
            "image_prompt": {"type": "string"}, "slides": {"type": "array", "items": {"type": "object"}}},
            "required": ["placement_id", "type", "title"]}}}, "required": ["creatives"]}}},
    {"type": "function", "function": {
        "name": "propose_save",
        "description": "Предложить менеджеру сохранить кампанию в БД.",
        "parameters": {"type": "object", "properties": {}}}},
]


@dataclass
class Session:
    id: str
    draft: dict = field(default_factory=lambda: {"field_sources": {}})
    messages: list = field(default_factory=list)
    pending: dict = field(default_factory=dict)  # action_id -> action
    missing: list = field(default_factory=list)


SESSIONS: dict[str, Session] = {}


class Agent:
    def __init__(self, backend: Backend | None = None):
        self.be = backend or Backend()
        self.llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY) if LLM_API_KEY else None

    def session(self, sid: str | None) -> Session:
        if sid and sid in SESSIONS:
            return SESSIONS[sid]
        s = Session(id=sid or uuid.uuid4().hex[:12])
        s.messages.append({"role": "system", "content": SYSTEM_PROMPT.format(today=date.today().isoformat())})
        SESSIONS[s.id] = s
        return s

    # ---------- диалог ----------
    def chat(self, sid: str | None, text: str) -> dict:
        s = self.session(sid)
        s.draft.setdefault("source_request", text)
        s.messages.append({"role": "user", "content": text})
        if not self.llm:
            return self._mock(s)
        reply = ""
        for _ in range(MAX_STEPS):
            resp = self.llm.chat.completions.create(model=LLM_MODEL, messages=s.messages, tools=TOOLS, temperature=0.3)
            msg = resp.choices[0].message
            s.messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                reply = msg.content or ""
                break
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = self._tool(s, tc.function.name, args)
                except Exception as e:  # ошибка инструмента уходит модели, а не пользователю
                    result = {"error": str(e)}
                s.messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)})
        return self._state(s, reply)

    def _tool(self, s: Session, name: str, a: dict):
        if name == "get_reference":
            return getattr(self.be, a["kind"])()
        if name == "find_campaigns":
            return self.be.campaigns(**a)
        if name == "update_draft":
            fields = a.get("fields", {})
            sources = fields.pop("field_sources", {}) or {}
            fields.pop("id", None)
            s.draft.update(fields)
            s.draft["field_sources"].update(sources)
            v = self.be.validate(s.draft)
            s.missing = v["missing"]
            return {"draft": s.draft, "missing": v["missing"], "problems": v["problems"]}
        if name == "propose_segment":
            return self._propose(s, "create_segment", a, f"Создать сегмент «{a['name']}»")
        if name == "propose_advertiser":
            return self._propose(s, "create_advertiser", a, f"Создать рекламодателя «{a['name']}»")
        if name == "generate_creatives":
            placements = {p["id"]: p for p in self.be.placements()}
            out = []
            for c in a["creatives"]:
                pl = placements.get(c["placement_id"])
                prompt = c.pop("image_prompt", "") or c["title"]
                if c["type"] != "push":
                    c["image_url"] = make_image(prompt, c["title"], (pl or {}).get("size"))
                c["id"] = "cr_" + uuid.uuid4().hex[:8]
                c["issues"] = check(c, pl)
                out.append(c)
            s.draft["creatives"] = out
            return [{k: v for k, v in c.items() if k != "image_url"} for c in out]
        if name == "propose_save":
            return self._propose(s, "save_campaign", {}, "Сохранить кампанию в БД")
        return {"error": f"unknown tool {name}"}

    def _propose(self, s: Session, kind: str, payload: dict, title: str):
        aid = uuid.uuid4().hex[:8]
        s.pending[aid] = {"id": aid, "kind": kind, "title": title, "payload": payload}
        return {"pending_action": aid, "note": "ждёт подтверждения менеджера"}

    # ---------- подтверждение ----------
    def confirm(self, sid: str, action_id: str, approved: bool) -> dict:
        s = SESSIONS[sid]
        act = s.pending.pop(action_id)
        if not approved:
            note = f"Менеджер отклонил действие: {act['title']}."
        elif act["kind"] == "create_segment":
            seg = self.be.create_segment(act["payload"])
            s.draft["segment_ids"] = list({*s.draft.get("segment_ids", []), seg["id"]})
            note = f"Сегмент создан: {seg['id']}, добавлен в кампанию."
        elif act["kind"] == "create_advertiser":
            adv = self.be.create_advertiser(act["payload"])
            s.draft["advertiser_id"] = adv["id"]
            note = f"Рекламодатель создан: {adv['id']}, привязан к кампании."
        else:
            res = self.be.save_campaign(s.draft)
            s.draft = res["campaign"]
            note = f"Кампания сохранена: {s.draft['id']}, статус {s.draft['status']}."
        s.missing = self.be.validate(s.draft)["missing"]
        # сообщаем агенту, чтобы он продолжил диалог с учётом результата
        s.messages.append({"role": "user", "content": f"[система] {note}"})
        return self._state(s, note)

    def _state(self, s: Session, reply: str) -> dict:
        return {
            "session_id": s.id,
            "reply": reply,
            "draft": s.draft,
            "missing": s.missing,
            "pending_actions": list(s.pending.values()),
        }

    def _mock(self, s: Session) -> dict:
        """Режим без ключа LLM — чтобы фронт мог интегрироваться заранее."""
        v = self.be.validate(s.draft)
        s.missing = v["missing"]
        reply = "LLM не подключена (нет LLM_API_KEY). Не хватает полей: " + ", ".join(v["missing"])
        return self._state(s, reply)
