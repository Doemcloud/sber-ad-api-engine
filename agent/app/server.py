"""HTTP-обёртка агента для фронтенда."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import SESSIONS, Agent
from .api_client import ApiClient
from .llm import from_env
from .tools import schemas

app = FastAPI(title="AI-ассистент рекламных кампаний")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
agent = Agent(ApiClient(), from_env())


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
def chat(body: ChatIn):
    return agent.chat(body.session_id, body.message, body.user, body.role)


@app.post("/confirm")
def confirm(body: ConfirmIn):
    try:
        return agent.confirm(body.session_id, body.action_id, body.approved, body.note)
    except KeyError as e:
        raise HTTPException(404, str(e)) from None


@app.post("/sessions/{sid}/role")
def set_role(sid: str, body: RoleIn):
    s = agent.session(sid, body.user, body.role)
    agent.log(s, "role_changed", {"user": body.user, "role": body.role})
    return agent.state(s, "")


@app.post("/sessions/{sid}/campaign/{cid}")
def open_campaign(sid: str, cid: int):
    s = agent.session(sid)
    s.campaign_id = cid
    return agent.state(s, "")


@app.get("/sessions/{sid}")
def get_session(sid: str):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "сессия не найдена")
    return agent.state(s, "")
