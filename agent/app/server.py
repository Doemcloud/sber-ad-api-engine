"""HTTP-обёртка агента для фронтенда."""
from __future__ import annotations

import os
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import SESSIONS, Agent, load_sessions, save_sessions
from .api_client import ApiClient, ApiError
from .llm import from_env
from .tools import schemas

app = FastAPI(title="AI-ассистент рекламных кампаний")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
agent = Agent(ApiClient(), from_env())
load_sessions()  # история диалогов переживает перезапуск

# Вход: при AUTH_REQUIRED=1 каждый запрос несёт токен пользователя; кто он и какая у него роль,
# агент узнаёт у API кампаний (/auth/me), а не из тела запроса — подменить роль из браузера нельзя.
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "0") == "1"
_ME: dict[str, tuple[float, dict]] = {}


def who(authorization: str | None) -> dict | None:
    tok = (authorization or "")[7:].strip() if (authorization or "").lower().startswith("bearer ") else ""
    if not tok:
        if AUTH_REQUIRED:
            raise HTTPException(401, "Войдите в рекламный кабинет")
        return None
    hit = _ME.get(tok)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        u = agent.api.me(tok)
    except ApiError as e:
        raise HTTPException(401 if e.status != 503 else 503, e.errors[0]["message"]) from None
    _ME[tok] = (time.time(), u)
    return u


def manager_only(me: dict | None) -> None:
    """Ассистент — инструмент менеджера кампаний; у модератора своего чата нет."""
    if me and me.get("role") != "campaignManager":
        raise HTTPException(403, "Ассистент доступен менеджеру кампаний")


def own(sid: str, me: dict | None):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "сессия не найдена")
    if me and s.user != me["user"]:
        raise HTTPException(403, "Это чужой диалог")
    return s


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str
    user: str | None = None
    role: str | None = None


class ConfirmIn(BaseModel):
    session_id: str
    action_id: str
    approved: bool = True
    note: str = ""


class RoleIn(BaseModel):
    user: str
    role: str


@app.get("/health")
def health():
    return {"status": "ok", "llm": type(agent.llm).__name__}


@app.get("/tools")
def tools():
    """Описание инструментов агента (JSON-схемы) — артефакт поставки §8."""
    return schemas()


@app.post("/chat")
def chat(body: ChatIn, authorization: str | None = Header(default=None)):
    me = who(authorization)
    manager_only(me)
    if me and body.session_id in SESSIONS:
        own(body.session_id, me)
    user, role = (me["user"], me["role"]) if me else (body.user, body.role)
    return agent.chat(body.session_id, body.message, user, role)


@app.post("/confirm")
def confirm(body: ConfirmIn, authorization: str | None = Header(default=None)):
    me = who(authorization)
    manager_only(me)
    if me:
        own(body.session_id, me)
    try:
        return agent.confirm(body.session_id, body.action_id, body.approved, body.note)
    except KeyError as e:
        raise HTTPException(404, str(e)) from None


@app.post("/sessions/{sid}/role")
def set_role(sid: str, body: RoleIn, authorization: str | None = Header(default=None)):
    me = who(authorization)
    if me:
        body = RoleIn(user=me["user"], role=me["role"])
        if sid in SESSIONS:
            own(sid, me)
    s = agent.session(sid, body.user, body.role)
    agent.log(s, "role_changed", {"user": body.user, "role": body.role})
    save_sessions()
    return agent.state(s, "")


@app.post("/sessions/{sid}/campaign/{cid}")
def open_campaign(sid: str, cid: int, authorization: str | None = Header(default=None)):
    me = who(authorization)
    if me and sid in SESSIONS:
        own(sid, me)
    s = agent.session(sid, me["user"] if me else None, me["role"] if me else None)
    s.campaign_id = cid
    save_sessions()
    return agent.state(s, "")


@app.get("/sessions")
def list_sessions(user: str | None = None, authorization: str | None = Header(default=None)):
    """История диалогов (панель «История» в разделе ассистента): у каждого — только свои."""
    me = who(authorization)
    manager_only(me)
    return agent.history(me["user"] if me else user)


@app.delete("/sessions/{sid}")
def delete_session(sid: str, authorization: str | None = Header(default=None)):
    own(sid, who(authorization))
    SESSIONS.pop(sid, None)
    save_sessions()
    return {"deleted": sid}


@app.get("/sessions/{sid}")
def get_session(sid: str, authorization: str | None = Header(default=None)):
    return agent.state(own(sid, who(authorization)), "")
