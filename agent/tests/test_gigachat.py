"""Адаптер GigaChat против эмулятора протокола (OAuth + /chat/completions с functions).
Живой GigaChat из CI недоступен; эмулятор проверяет то, на чём адаптер обычно ломается:
Basic-ключ и scope в OAuth, Bearer-токен, обновление токена по 401, формат function_call
и то, что результат функции уходит JSON-объектом."""
import base64
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from app import llm
from app.agent import clip_json

CID, SECRET = "client-id-123", "secret-456"
KEY = base64.b64encode(f"{CID}:{SECRET}".encode()).decode()


class Fake(BaseHTTPRequestHandler):
    tokens_issued = 0
    expire_next = False
    requests: list = []

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"])).decode()
        if self.path == "/oauth":
            assert self.headers["Authorization"] == f"Basic {KEY}", self.headers["Authorization"]
            assert self.headers.get("RqUID"), "нет RqUID"
            assert parse_qs(raw)["scope"] == ["GIGACHAT_API_PERS"]
            Fake.tokens_issued += 1
            return self._send(200, {"access_token": f"tok{Fake.tokens_issued}", "expires_at": 4102444800000})
        if self.path == "/v1/chat/completions":
            if self.headers["Authorization"] != f"Bearer tok{Fake.tokens_issued}" or Fake.expire_next:
                Fake.expire_next = False
                return self._send(401, {"message": "Token has expired"})
            body = json.loads(raw)
            Fake.requests.append(body)
            assert body["model"] == "GigaChat-3-Ultra"
            assert body["function_call"] == "auto" and body["functions"]
            msgs = body["messages"]
            for i, m in enumerate(msgs):
                if m["role"] == "function":
                    assert isinstance(json.loads(m["content"]), dict), "результат функции должен быть JSON-объектом"
                    assert msgs[i - 1].get("function_call", {}).get("name") == m["name"]
            if msgs[-1]["role"] == "user":
                return self._send(200, {"choices": [{"finish_reason": "function_call", "message": {
                    "role": "assistant", "content": "", "functions_state_id": "st-1",
                    "function_call": {"name": "get_places", "arguments": {}}}}]})
            assert msgs[-2].get("functions_state_id") == "st-1"
            return self._send(200, {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Готово"}}]})
        self._send(404, {})


class GigaChatAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        port = cls.srv.server_address[1]
        cls.env = {"LLM_PROVIDER": "gigachat", "GIGACHAT_CLIENT_ID": CID, "GIGACHAT_CLIENT_SECRET": SECRET,
                   "GIGACHAT_OAUTH_URL": f"http://127.0.0.1:{port}/oauth", "GIGACHAT_BASE_URL": f"http://127.0.0.1:{port}/v1"}
        cls.saved = {k: os.environ.get(k) for k in list(cls.env) + ["GIGACHAT_AUTH_KEY", "LLM_MODEL"]}
        os.environ.update(cls.env)
        os.environ.pop("GIGACHAT_AUTH_KEY", None)
        os.environ.pop("LLM_MODEL", None)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_round_trip_with_function_call_and_token_refresh(self):
        model = llm.from_env()
        self.assertIsInstance(model, llm.GigaChat)
        self.assertEqual(model.auth_key, KEY)  # ключ собран из client id + secret
        tools = [{"name": "get_places", "description": "Места размещения", "parameters": {"type": "object", "properties": {}}}]
        history = [{"role": "system", "content": "Ты ассистент"}, {"role": "user", "content": "Какие есть места?"}]
        r1 = model.complete(history, tools)
        self.assertEqual(r1["tool_calls"][0]["name"], "get_places")
        call = r1["tool_calls"][0]
        history += [{"role": "assistant", "content": "", "tool_calls": [call]},
                    {"role": "tool", "tool_call_id": call["id"], "name": "get_places",
                     "content": json.dumps([{"id": 1, "description": "Промо-блок"}], ensure_ascii=False)}]
        Fake.expire_next = True  # следующий запрос получит 401 — адаптер обязан обновить токен
        r2 = model.complete(history, tools)
        self.assertEqual(r2["content"], "Готово")
        self.assertEqual(Fake.tokens_issued, 2)

    def test_clip_json_always_valid(self):
        big = [{"id": i, "text": "x" * 200} for i in range(500)]
        out = json.loads(clip_json(big))
        self.assertLess(out["shown"], 500)
        self.assertEqual(out["total"], 500)
        self.assertTrue(json.loads(clip_json({"t": "y" * 50000}))["truncated"])


if __name__ == "__main__":
    unittest.main()
