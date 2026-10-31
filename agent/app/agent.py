"""Агент: цикл tool calling, состояние сессии, план пишущих действий с
подтверждением человека (task.md §6.2).

Гарантии, которые держит код, а не промпт:
- пишущие инструменты не вызывают API — они ставят шаги в план; API
  вызывается только в confirm() после явного подтверждения;
- JSON баннера/контента, enum и id проверяются до постановки в план;
- ошибки API (400/404) возвращаются модели и пользователю с подсказкой;
- каждое действие пишется в журнал агента (кто, что, когда).
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from . import validators as V
from .api_client import ApiClient, ApiError
from .explain import explain
from .compliance import check_creative, check_message
from .llm import LLM
from .tools import TOOLS, schemas

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "30"))  # GigaChat вызывает по одной функции за ответ
FORMAT_RU = {"STORY": "сторис", "SMART_BANNER": "смарт-баннер"}
CHANNEL_RU = {"iOS": "iOS", "ANDROID": "Android", "WEB": "веб-версия"}
HEADER_KEYS = ["name", "marketingName", "startDate", "startTime", "endDate", "endTime", "topic", "tags",
               "keywords", "audienceType", "weight", "initialCtr", "places"]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


_PATH_PARAM = re.compile(r"{(\w+)}")


def fill_path(path: str, args: dict) -> str:
    """Подставляет id в путь API. Принимаются только целые числа — модель не может
    подсунуть «101/../auth» и попасть в чужой эндпоинт."""
    def one(m):
        v = args[m.group(1)]
        if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.isdigit())):
            raise ValueError(f"{m.group(1)} должен быть числом, получено {v!r}")
        return str(int(v))
    return _PATH_PARAM.sub(one, path)


def stamp() -> str:
    """Время с микросекундами — для сортировки истории диалогов."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def clip_json(result, limit: int = 12000) -> str:
    """Результат инструмента для модели: всегда валидный JSON, даже если обрезан."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    if isinstance(result, list):
        n = len(result)
        while n > 1 and len(text) > limit:
            n //= 2
            text = json.dumps({"items": result[:n], "shown": n, "total": len(result)}, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return text
    return json.dumps({"truncated": True, "preview": text[: limit - 100]}, ensure_ascii=False)


@dataclass
class Session:
    id: str
    user: str = "ivanov.p"
    role: str = "campaignManager"
    messages: list = field(default_factory=list)
    campaign_id: int | None = None
    refs: dict = field(default_factory=dict)  # имя ссылки → id созданной сущности
    plan: list = field(default_factory=list)  # шаги, собранные в текущем ходе
    pending: dict | None = None  # план, ждущий подтверждения
    journal: list = field(default_factory=list)
    last_result: list = field(default_factory=list)
    title: str = ""
    created_at: str = field(default_factory=lambda: now())
    updated_at: str = field(default_factory=lambda: stamp())
    transcript: list = field(default_factory=list)  # лента для UI: реплики, итоги выполнения — для истории
    awaiting_fix: dict | None = None  # менеджер отменил план — ждём, что исправить


SESSIONS: dict[str, Session] = {}
_STORE_LOCK = threading.Lock()


def sessions_file() -> Path | None:
    v = os.getenv("SESSIONS_FILE", str(Path(__file__).resolve().parent.parent / "state" / "sessions.json"))
    return Path(v) if v else None


def save_sessions() -> None:
    """Снимок всех диалогов на диск: история переживает перезапуск агента."""
    path = sessions_file()
    if not path:
        return
    with _STORE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: asdict(v) for k, v in SESSIONS.items()}, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)


def load_sessions() -> int:
    path = sessions_file()
    if not path or not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    known = {f.name for f in fields(Session)}
    for k, v in raw.items():
        SESSIONS[k] = Session(**{x: y for x, y in v.items() if x in known})
    return len(raw)


class Agent:
    def __init__(self, api: ApiClient, llm: LLM, prompt_path: Path = PROMPT_PATH):
        self.api, self.llm = api, llm
        self.prompt = prompt_path.read_text(encoding="utf-8")
        turn = prompt_path.parent / "turn.md"
        # Служебная памятка, которая уходит модели вместе с каждым сообщением менеджера.
        # В историю диалога и во фронт не попадает.
        self.turn = turn.read_text(encoding="utf-8").strip() if turn.exists() else ""
        self.tools = schemas()
        self._dicts: dict | None = None

    # ------------------------------------------------------------------ сессия
    def session(self, sid: str | None, user: str | None = None, role: str | None = None) -> Session:
        s = SESSIONS.get(sid or "")
        if s is None:
            s = Session(id=sid or uuid.uuid4().hex[:12])
            SESSIONS[s.id] = s
        if user:
            s.user = user
        if role:
            s.role = role
        return s

    def log(self, s: Session, event: str, detail):
        s.journal.append({"at": now(), "actor": s.user, "role": s.role, "event": event, "detail": detail})

    def dicts(self, refresh: bool = False) -> dict:
        if self._dicts is None or refresh:
            d = {}
            for key, path in (("topics", "/topics"), ("tags", "/tags"), ("channels", "/channels"),
                              ("banner_types", "/banner-types"), ("segments", "/segments"), ("places", "/places")):
                d[key] = self.api.get(path)
            self._dicts = d
        return self._dicts

    def _system(self, s: Session) -> dict:
        camp = f"id {s.campaign_id}" if s.campaign_id else "не выбрана"
        text = self.prompt.format(today=datetime.now(timezone.utc).date().isoformat(), user=s.user, role=s.role, campaign=camp)
        return {"role": "system", "content": text}

    # ------------------------------------------------------------------ диалог
    def _outgoing(self, s: Session) -> list[dict]:
        """Что уходит модели: системный промпт + история, а к последнему сообщению
        менеджера — служебная памятка. Копия: сохранённая история не меняется."""
        msgs = [self._system(s)] + [dict(m) for m in s.messages]
        if self.turn:
            for m in reversed(msgs):
                if m["role"] == "user":
                    m["content"] = f"{m['content']}\n\n{self.turn}"
                    break
        return msgs

    def note(self, s: Session, item: dict) -> None:
        s.transcript.append({**item, "at": now()})
        s.updated_at = stamp()

    def chat(self, sid: str | None, text: str, user: str | None = None, role: str | None = None) -> dict:
        s = self.session(sid, user, role)
        if s.awaiting_fix:  # это ответ на «что не так с планом?»
            fix, s.awaiting_fix = s.awaiting_fix, None
            s.messages.append({"role": "user", "content": (
                f"[система] Причина отмены плана «{fix['title']}» (шаги: {'; '.join(fix['steps'])}). "
                f"Исправь по замечанию, остальное оставь, при необходимости уточни и собери исправленный план целиком.\n\n"
                f"Замечание менеджера: {text}")})
        else:
            s.messages.append({"role": "user", "content": text})
        self.log(s, "user_message", text)
        if not s.title:
            s.title = text.strip().replace("\n", " ")[:80]
        self.note(s, {"kind": "user", "text": text})
        save_sessions()  # реплика менеджера сохранена ещё до ответа модели
        block = check_message(text)
        if block:  # стоп-тема по закону о рекламе: отказ без обращения к модели
            self.log(s, "compliance_refusal", block["id"])
            s.awaiting_fix = None
            s.messages.append({"role": "assistant", "content": block["reply"]})
            self.note(s, {"kind": "assistant", "text": block["reply"]})
            save_sessions()
            return self.state(s, block["reply"])
        reply = self._run(s)
        if reply:
            self.note(s, {"kind": "assistant", "text": reply})
        save_sessions()
        return self.state(s, reply)

    def _run(self, s: Session) -> str:
        s.plan = []
        reply = ""
        start = len(s.messages)
        for _ in range(MAX_STEPS):
            try:
                resp = self.llm.complete(self._outgoing(s), self.tools)
            except Exception as e:  # лимиты/сеть модели: ответить человеку, а не уронить сервис
                self.log(s, "llm_error", str(e)[:300])
                del s.messages[start:]  # недоделанный ход не оставляем в истории модели
                s.plan = []
                busy = "429" in str(e) or "Too Many" in str(e)
                reply = ("GigaChat сейчас перегружен запросами — я не успел закончить. Повторите сообщение через минуту."
                         if busy else "Не удалось связаться с моделью. Повторите сообщение чуть позже.")
                s.messages.append({"role": "assistant", "content": reply})
                return reply
            calls = resp.get("tool_calls") or []
            s.messages.append({"role": "assistant", "content": resp.get("content") or "", "tool_calls": calls})
            if not calls:
                reply = resp.get("content") or ""
                break
            for c in calls:
                result = self.call_tool(s, c["name"], c.get("arguments") or {})
                s.messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                                   "content": clip_json(result)})
        else:
            reply = "Слишком много шагов подряд — остановился. Уточните задачу."
        if s.plan:
            s.pending = {"id": uuid.uuid4().hex[:8], "created_at": now(), "steps": s.plan,
                         "title": "; ".join(st["summary"] for st in s.plan[:3]) + ("…" if len(s.plan) > 3 else "")}
            self.log(s, "plan_proposed", [st["summary"] for st in s.plan])
            s.plan = []
        return reply

    # ------------------------------------------------------------------ инструменты
    def call_tool(self, s: Session, name: str, args: dict):
        spec = TOOLS.get(name)
        if spec is None:
            return {"ok": False, "errors": [{"code": "UNKNOWN_TOOL", "message": f"нет инструмента {name}"}]}
        kind, method, path = spec[0], spec[1], spec[2]
        self.log(s, "tool_call", {"tool": name, "args": args})
        try:
            if kind == "read":
                if "campaign_id" in args:
                    s.campaign_id = int(args["campaign_id"])
                return self.api.get(fill_path(path, args), user=s.user, role=s.role)
            if kind == "local":
                return self._local(name, args)
            return self._propose(s, name, args)
        except ApiError as e:
            return {"ok": False, "status": e.status, "errors": explain(e.errors)}
        except (KeyError, ValueError, TypeError) as e:
            return {"ok": False, "errors": [{"code": "BAD_ARGUMENTS", "message": f"неверные параметры: {e}"}]}

    def _banner_type(self, type_id) -> dict | None:
        return next((b for b in self.dicts()["banner_types"] if b["id"] == type_id), None)

    def _local(self, name: str, a: dict):
        if name == "validate_banner":
            errs = V.validate_banner("preview", self._banner_type(a.get("bannerTypeId")), a.get("content"))
        else:
            errs = V.validate_content("preview", "PROMO", a.get("content"))
        errs = errs + check_creative({"content": a.get("content")})
        return {"ok": not errs, "errors": explain(errs)}

    # ---- постановка шага в план с предварительной проверкой
    def _is_ref(self, s: Session, v) -> bool:
        if not (isinstance(v, str) and v.startswith("$")):
            return False
        name = v[1:]
        return name in s.refs or any(st.get("ref") == name for st in s.plan)

    def _planned(self, s: Session, ref: str) -> dict | None:
        return next((st for st in s.plan if st.get("ref") == ref.lstrip("$")), None)

    def _norm_id(self, s: Session, v):
        if isinstance(v, str) and v.startswith("$"):
            if not self._is_ref(s, v):
                raise ValueError(f"ссылка {v} не определена: задайте ref у шага, который создаёт эту сущность")
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v)
        if isinstance(v, float):
            return int(v)
        return v

    def _campaign_header(self, s: Session, cid) -> dict:
        """Текущая шапка кампании (сырые значения) — из API или из плана."""
        if isinstance(cid, str):
            st = self._planned(s, cid)
            return copy.deepcopy(st["args"]["campaign"]) if st and st["tool"] == "create_campaign" else {}
        det = self.api.get(f"/campaigns/{cid}", user=s.user, role=s.role)
        return {k: det.get(k) for k in HEADER_KEYS if det.get(k) is not None}

    def _propose(self, s: Session, name: str, a: dict):
        a = copy.deepcopy(a)
        role = TOOLS[name][3]
        if role and s.role != role:
            errs = [{"code": "ROLE_FORBIDDEN", "message": f"инструмент {name} доступен роли {role}, текущая роль {s.role}"}]
            return {"ok": False, "errors": explain(errs)}
        for k in ("campaign_id", "banner_id", "content_id", "creative_id", "bannerId", "contentId"):
            if k in a and a[k] is not None:
                a[k] = self._norm_id(s, a[k])
        d = self.dicts()
        errs: list[dict] = []
        preview: dict = {}

        if name in ("create_campaign", "update_campaign"):
            c = a.get("campaign") or {}
            for k in ("tags", "places"):
                if k in c:
                    c[k] = [self._norm_id(s, v) for v in c[k] or []]
            merged = c if name == "create_campaign" else {**self._campaign_header(s, a["campaign_id"]), **c}
            if name == "create_campaign":
                merged.setdefault("weight", 0)
                merged.setdefault("initialCtr", 15)
            a["campaign"] = merged
            errs = V.validate_header(merged, d, refs_ok=lambda v: self._is_ref(s, v))
            preview = {"kind": "campaign", "data": merged}
            summary = f"{'Создать' if name == 'create_campaign' else 'Изменить'} кампанию «{merged.get('name')}»"
        elif name == "set_segments":
            inc, exc = a.get("included") or [], a.get("excluded") or []
            audience = self._campaign_header(s, a["campaign_id"]).get("audienceType")
            errs = V.validate_segments(audience, inc, exc, d)
            if audience == "SEGMENTED" and not inc:
                errs.append(V.err("SEGMENTS_REQUIRED", "segments.included", "для SEGMENTED нужен хотя бы один сегмент включения"))
            seg = {x["code"]: x for x in d["segments"]}
            preview = {"kind": "segments", "data": {"included": [seg.get(c, {"code": c}) for c in inc],
                                                    "excluded": [seg.get(c, {"code": c}) for c in exc]}}
            nm = lambda c: (seg.get(c, {}).get("name") or c).replace("Исключение. ", "")
            summary = f"Аудитория: {', '.join(nm(c) for c in inc) or 'без таргетинга'}" + (f"; исключить: {', '.join(nm(c).lower() for c in exc)}" if exc else "")
        elif name in ("create_banner", "update_banner"):
            if name == "update_banner":
                cur = self._child(s, a["campaign_id"], "banners", a["banner_id"])
                a = {**a, "name": a.get("name", cur.get("name")), "bannerTypeId": a.get("bannerTypeId", cur.get("bannerTypeId")),
                     "content": a.get("content", cur.get("content"))}
            bt = self._banner_type(a.get("bannerTypeId"))
            errs = V.validate_banner(a.get("name", ""), bt, a.get("content"))
            preview = {"kind": "banner", "bannerType": (bt or {}).get("code"), "data": {"name": a.get("name"), "content": a.get("content")}}
            summary = f"{'Создать' if name == 'create_banner' else 'Изменить'} {FORMAT_RU.get((bt or {}).get('code'), 'баннер')} «{a.get('name')}»"
        elif name in ("create_content", "update_content"):
            if name == "update_content":
                cur = self._child(s, a["campaign_id"], "contents", a["content_id"])
                a = {**a, "name": a.get("name", cur.get("name")), "content": a.get("content", cur.get("content"))}
            errs = V.validate_content(a.get("name", ""), "PROMO", a.get("content"))
            preview = {"kind": "content", "data": {"name": a.get("name"), "content": a.get("content")}}
            summary = f"{'Создать' if name == 'create_content' else 'Изменить'} промо-экран «{a.get('name')}»"
        elif name in ("create_creative", "update_creative"):
            if name == "update_creative":
                cur = self._child(s, a["campaign_id"], "creatives", a["creative_id"])
                a = {**{k: cur.get(k) for k in ("name", "bannerId", "contentId", "channelCode")}, **{k: v for k, v in a.items() if v is not None}}
            errs = self._check_creative(s, a, d)
            preview = {"kind": "creative", "data": {k: a.get(k) for k in ("name", "bannerId", "contentId", "channelCode")}}
            lbl = lambda v, new, old: new if isinstance(v, str) else f"{old} {v}"
            summary = f"Разместить на платформе {CHANNEL_RU.get(a.get('channelCode'), a.get('channelCode'))}: {lbl(a.get('bannerId'), 'новый баннер', 'баннер')}" + (
                f" + {lbl(a.get('contentId'), 'новый промо-экран', 'промо-экран')}" if a.get("contentId") else "")
        elif name in ("create_place", "create_tag"):
            if name == "create_place":
                if not a.get("code") or not a.get("description"):
                    errs.append(V.err("PLACE_CODE_REQUIRED", "code", "нужны code и description"))
                elif any(p["code"] == a["code"] for p in d["places"]):
                    errs.append(V.err("PLACE_CODE_DUPLICATE", "code", f"место {a['code']} уже есть — используйте его"))
                summary = f"Добавить место размещения «{a.get('description')}»"
            else:
                if not a.get("name"):
                    errs.append(V.err("TAG_NAME_REQUIRED", "name", "нужно название тега"))
                elif any(t["name"].lower() == a["name"].lower() for t in d["tags"]):
                    errs.append(V.err("TAG_NAME_DUPLICATE", "name", f"тег «{a['name']}» уже есть — используйте его id"))
                summary = f"Создать тег «{a.get('name')}»"
            preview = {"kind": name.replace("create_", ""), "data": {k: v for k, v in a.items() if k != "ref"}}
        elif name == "to_moderation":
            if not isinstance(a["campaign_id"], str):
                v = self.api.get(f"/campaigns/{a['campaign_id']}/warnings", user=s.user, role=s.role)
                if v["errors"] and not s.plan:  # если в плане есть правки, проверка будет после них
                    errs = v["errors"]
            summary = "Отправить кампанию на модерацию"
            preview = {"kind": "transition", "to": "ON_MODERATION"}
        elif name == "resume":
            why = (a.get("comment") or "").strip()
            summary = "Запросить возобновление показов — кампания уйдёт модератору" + (f" с пояснением «{why}»" if why else "")
            preview = {"kind": "transition", "to": "ON_MODERATION"}
        elif name == "decline":
            if not (a.get("comment") or "").strip():
                errs.append(V.err("DECLINE_COMMENT_REQUIRED", "comment", "нужен комментарий модератора"))
            summary = f"Вернуть кампанию на доработку с комментарием «{a.get('comment')}»"
            preview = {"kind": "transition", "to": "NEEDS_WORK", "comment": a.get("comment")}
        else:  # approve, activate, stop, delete_*
            labels = {"approve": "Одобрить кампанию", "activate": "Запустить кампанию — реклама появится в приложении",
                      "stop": "Остановить показы кампании", "delete_campaign": "Удалить кампанию",
                      "delete_banner": "Удалить баннер", "delete_content": "Удалить промо-экран", "delete_creative": "Убрать креатив с платформы"}
            summary = labels.get(name, name)
            preview = {"kind": "transition" if not name.startswith("delete") else "delete", "tool": name}

        if name in ("create_campaign", "update_campaign", "create_banner", "update_banner", "create_content", "update_content"):
            law = check_creative({k: v for k, v in a.items() if k in ("campaign", "name", "marketingName", "keywords", "content")})
            if law:  # стоп-темы и недостоверная реклама — шаг не попадает в план
                self.log(s, "compliance_rejected_step", {"tool": name})
                errs = errs + law
        if errs:
            self.log(s, "step_rejected_by_validation", {"tool": name, "errors": errs})
            return {"ok": False, "errors": explain(errs)}
        step = {"n": len(s.plan) + 1, "tool": name, "args": a, "ref": a.get("ref"), "summary": summary, "preview": preview}
        s.plan.append(step)
        return {"ok": True, "queued": True, "step": step["n"], "ref": step["ref"],
                "note": "Шаг добавлен в план и будет выполнен после подтверждения менеджера."}

    def _child(self, s: Session, cid, coll: str, item_id) -> dict:
        det = self.api.get(f"/campaigns/{cid}", user=s.user, role=s.role)
        item = next((x for x in det.get(coll, []) if x["id"] == item_id), None)
        if item is None:
            raise ValueError(f"{coll[:-1]} {item_id} не найден в кампании {cid}")
        return item

    def _check_creative(self, s: Session, a: dict, d: dict) -> list[dict]:
        errs = []
        channels = {c["code"] for c in d["channels"]}
        if a.get("channelCode") not in channels:
            errs.append(V.err("ENTITY_NOT_FOUND", "channelCode", f"канал {a.get('channelCode')!r}; допустимо {', '.join(sorted(channels))} (регистр важен)"))
        bid = a.get("bannerId")
        if isinstance(bid, str):
            st = self._planned(s, bid)
            type_id = st["args"].get("bannerTypeId") if st else None
        else:
            cid = a.get("campaign_id")
            det = self.api.get(f"/campaigns/{cid}", user=s.user, role=s.role) if not isinstance(cid, str) else {"banners": []}
            b = next((x for x in det.get("banners", []) if x["id"] == bid), None)
            type_id = b["bannerTypeId"] if b else None
            if b is None:
                errs.append(V.err("ENTITY_NOT_FOUND", "bannerId", f"баннера {bid} нет в кампании"))
        bt = self._banner_type(type_id)
        if bt and a.get("channelCode") not in bt["channels"]:
            errs.append(V.err("CREATIVE_CHANNEL_NOT_ALLOWED", "channelCode", f"{bt['code']} не показывается в {a.get('channelCode')}; допустимо {', '.join(bt['channels'])}"))
        dup = [st for st in s.plan if st["tool"] == "create_creative" and st["args"].get("bannerId") == bid and st["args"].get("channelCode") == a.get("channelCode")]
        if dup:
            errs.append(V.err("CREATIVE_DUPLICATE", "channelCode", "такой креатив уже есть в плане"))
        return errs

    # ------------------------------------------------------------------ подтверждение
    def confirm(self, sid: str, action_id: str, approved: bool, note: str = "") -> dict:
        s = SESSIONS[sid]
        if not s.pending or s.pending["id"] != action_id:
            raise KeyError("план не найден или уже обработан")
        plan, s.pending = s.pending, None
        if not approved:
            self.log(s, "plan_rejected", {"title": plan["title"], "note": note})
            self.note(s, {"kind": "result", "results": [], "rejected": plan["title"]})
            if note.strip():  # причину написали сразу — пересобираем план
                s.messages.append({"role": "user", "content": f"[система] Менеджер отменил план «{plan['title']}». Что исправить: {note}. Собери исправленный план."})
                return self._finish(s)
            # Причины нет — спрашиваем без обращения к модели и ждём ответа менеджера.
            s.awaiting_fix = {"title": plan["title"], "steps": [st["summary"] for st in plan["steps"]]}
            reply = ("План отменён, ничего не сохранено. Что не так? Напишите, что поправить — например, другие даты, "
                     "аудиторию, место размещения или текст баннера, — и я соберу исправленный план.")
            s.messages.append({"role": "user", "content": f"[система] Менеджер отменил план «{plan['title']}» и пока не сказал почему."})
            s.messages.append({"role": "assistant", "content": reply})
            self.note(s, {"kind": "assistant", "text": reply})
            save_sessions()
            return self.state(s, reply)
        self.log(s, "plan_approved", plan["title"])
        results, failed = [], None
        for st in plan["steps"]:
            try:
                res = self._execute(s, st)
                results.append({"step": st["n"], "summary": st["summary"], "ok": True, "id": (res or {}).get("id") if isinstance(res, dict) else None})
                self.log(s, "executed", {"step": st["summary"], "result_id": results[-1]["id"]})
            except ApiError as e:
                failed = {"step": st["n"], "summary": st["summary"], "ok": False, "status": e.status, "errors": explain(e.errors)}
                results.append(failed)
                self.log(s, "execution_failed", failed)
                break
            except (ValueError, KeyError) as e:
                failed = {"step": st["n"], "summary": st["summary"], "ok": False, "errors": [{"code": "BAD_ARGUMENTS", "message": str(e)}]}
                results.append(failed)
                break
        s.last_result = results
        report = {"results": results, "skipped": [st["summary"] for st in plan["steps"][len(results):]]}
        if s.campaign_id:
            try:
                det = self.api.get(f"/campaigns/{s.campaign_id}")
                report["campaign"] = {"id": det["id"], "state": det["state"], "published": det["published"]}
                report["validation"] = self.api.get(f"/campaigns/{s.campaign_id}/warnings")
            except ApiError:
                pass
        s.messages.append({"role": "user", "content": "[система] План подтверждён и выполнен: " + json.dumps(report, ensure_ascii=False)})
        self.note(s, {"kind": "result", "results": results})
        save_sessions()
        return self._finish(s)

    def _finish(self, s: Session) -> dict:
        reply = self._run(s)
        if reply:
            self.note(s, {"kind": "assistant", "text": reply})
        save_sessions()
        return self.state(s, reply)

    def _resolve(self, s: Session, v):
        if isinstance(v, str) and v.startswith("$"):
            if v[1:] not in s.refs:
                raise ValueError(f"ссылка {v} не разрешена — предыдущий шаг не выполнен")
            return s.refs[v[1:]]
        if isinstance(v, list):
            return [self._resolve(s, x) for x in v]
        if isinstance(v, dict):
            return {k: self._resolve(s, x) for k, x in v.items()}
        return v

    def _wrap_campaign(self, c: dict) -> dict:
        """Тело POST/PUT: словарные поля — объектами {value, label} (task.md §2.2)."""
        d = self.dicts(refresh=True)
        topics = {t["value"]: t["label"] for t in d["topics"]}
        tags = {t["id"]: t["name"] for t in d["tags"]}
        places = {p["id"]: p["code"] for p in d["places"]}
        body = {k: v for k, v in c.items() if k in HEADER_KEYS and v is not None}
        if "topic" in body:
            body["topic"] = {"value": body["topic"], "label": topics.get(body["topic"], body["topic"])}
        body["tags"] = [{"value": t, "label": tags.get(t, str(t))} for t in c.get("tags") or []]
        body["places"] = [{"value": p, "label": places.get(p, str(p))} for p in c.get("places") or []]
        return body

    def _execute(self, s: Session, st: dict):
        name, a = st["tool"], self._resolve(s, st["args"])
        method, path = TOOLS[name][1], TOOLS[name][2]
        url = fill_path(path, a)
        kw = {"user": s.user, "role": s.role}
        if "campaign_id" in a:
            s.campaign_id = a["campaign_id"]
        if name == "create_campaign":
            body = self._wrap_campaign(a["campaign"])
        elif name == "update_campaign":
            cur = self._campaign_header(s, a["campaign_id"])  # GET → слияние → PUT полного объекта
            body = self._wrap_campaign({**cur, **a["campaign"]})
        elif name == "set_segments":
            body = {"included": a.get("included") or [], "excluded": a.get("excluded") or []}
        elif name in ("create_banner", "update_banner"):
            body = {"name": a["name"], "bannerTypeId": a["bannerTypeId"], "content": a["content"]}
        elif name in ("create_content", "update_content"):
            body = {"name": a["name"], "contentType": "PROMO", "content": a["content"]}
        elif name in ("create_creative", "update_creative"):
            body = {k: a[k] for k in ("name", "bannerId", "channelCode")}
            if a.get("contentId") is not None:
                body["contentId"] = a["contentId"]
        elif name == "create_place":
            body = {"code": a["code"], "description": a["description"]}
        elif name == "create_tag":
            body = {"name": a["name"]}
        elif name == "resume":
            body = {"comment": (a.get("comment") or "").strip()}
        elif name == "decline":
            body = {"comment": a["comment"]}
        elif method == "POST":
            body = {}
        else:
            body = None
        res = self.api.request(method, url, body, **kw)
        if name == "create_campaign" and isinstance(res, dict):
            s.campaign_id = res["id"]
        if name in ("create_tag", "create_place"):
            self.dicts(refresh=True)
        if st.get("ref") and isinstance(res, dict) and "id" in res:
            s.refs[st["ref"]] = res["id"]
        return res

    def history(self, user: str | None = None) -> list[dict]:
        """Список диалогов для панели «История»: свежие сверху, пустые не показываем."""
        out, names = [], {}
        for x in SESSIONS.values():
            if not x.transcript or (user and x.user != user):
                continue
            if x.campaign_id and x.campaign_id not in names:
                try:
                    names[x.campaign_id] = self.api.get(f"/campaigns/{x.campaign_id}").get("name")
                except Exception:  # кампания удалена или API недоступен — история всё равно показывается
                    names[x.campaign_id] = None
            out.append({"id": x.id, "title": x.title or "Без названия", "updated_at": x.updated_at, "created_at": x.created_at,
                        "user": x.user, "campaign_id": x.campaign_id, "campaign_name": names.get(x.campaign_id),
                        "messages": sum(1 for t in x.transcript if t["kind"] == "user"), "pending": bool(x.pending)})
        return sorted(out, key=lambda r: r["updated_at"], reverse=True)

    # ------------------------------------------------------------------ состояние для UI
    def state(self, s: Session, reply: str) -> dict:
        out = {"session_id": s.id, "user": s.user, "role": s.role, "reply": reply, "title": s.title,
               "transcript": s.transcript,
               "campaign_id": s.campaign_id, "pending_action": s.pending, "awaiting_fix": bool(s.awaiting_fix), "last_result": s.last_result,
               "journal": s.journal[-30:]}
        if s.campaign_id:
            try:
                out["campaign"] = self.api.get(f"/campaigns/{s.campaign_id}")
                v = self.api.get(f"/campaigns/{s.campaign_id}/warnings")
                v["errors"] = explain(v.get("errors", []))
                v["warningDetails"] = explain(v.get("warningDetails", []))
                out["validation"] = v
            except ApiError:
                out["campaign"] = None
        return out
