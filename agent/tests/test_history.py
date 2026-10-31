"""История диалогов: лента сохраняется на диск и восстанавливается после перезапуска."""
import os
import tempfile
import unittest

from app import agent as A
from app.api_client import ApiClient


class Echo:
    def complete(self, messages, tools):
        return {"content": "Понял: " + messages[-1]["content"], "tool_calls": []}


class History(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("SESSIONS_FILE")
        os.environ["SESSIONS_FILE"] = os.path.join(self.tmp.name, "sessions.json")
        A.SESSIONS.clear()

    def tearDown(self):
        A.SESSIONS.clear()
        if self.saved is None:
            os.environ.pop("SESSIONS_FILE", None)
        else:
            os.environ["SESSIONS_FILE"] = self.saved
        self.tmp.cleanup()

    def test_dialog_survives_restart(self):
        a = A.Agent(ApiClient("http://127.0.0.1:9"), Echo())
        st = a.chat(None, "Кампания по вкладу", "ivanov.p", "campaignManager")
        a.chat(st["session_id"], "Сторис")
        a.chat(None, "Второй диалог", "petrova.m", "campaignModerator")

        A.SESSIONS.clear()  # «перезапуск» агента
        self.assertEqual(A.load_sessions(), 2)

        h = a.history()
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]["title"], "Второй диалог")  # свежие сверху
        self.assertEqual(len(a.history("ivanov.p")), 1)

        restored = a.state(A.SESSIONS[st["session_id"]], "")
        self.assertEqual([t["kind"] for t in restored["transcript"]], ["user", "assistant", "user", "assistant"])
        self.assertEqual(restored["title"], "Кампания по вкладу")
        st2 = a.chat(st["session_id"], "Продолжаем")  # диалог продолжается с контекстом модели
        self.assertEqual(len(A.SESSIONS[st["session_id"]].messages), 6)
        self.assertIn("Продолжаем", st2["reply"])


if __name__ == "__main__":
    unittest.main()
