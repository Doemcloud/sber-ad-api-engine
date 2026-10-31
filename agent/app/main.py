from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import SESSIONS, Agent

app = FastAPI(title="AdCamp AI Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
agent = Agent()


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str


class ConfirmIn(BaseModel):
    session_id: str
    action_id: str
    approved: bool = True


@app.get("/health")
def health():
    return {"status": "ok", "llm": bool(agent.llm)}


@app.post("/chat")
def chat(body: ChatIn):
    return agent.chat(body.session_id, body.message)


@app.post("/confirm")
def confirm(body: ConfirmIn):
    s = SESSIONS.get(body.session_id)
    if not s or body.action_id not in s.pending:
        raise HTTPException(404, "действие не найдено")
    return agent.confirm(body.session_id, body.action_id, body.approved)


@app.get("/sessions/{sid}")
def session(sid: str):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "сессия не найдена")
    return agent._state(s, "")
