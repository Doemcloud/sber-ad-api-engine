"""Нейрогенерация изображений: протокол text2image GigaChat (эмулятор), демо-генератор, выбор провайдера."""
import json
import os
import struct
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from app import images
from app.images import DemoImages, GigaChatImages, ImageUnavailable, build_prompt

FILE_ID = "a598ae3d-d3eb-454e-a8bf-0848193a603e"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64


class Fake(BaseHTTPRequestHandler):
    bodies: list = []
    refuse = False

    def log_message(self, *a):
        pass

    def _json(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"])).decode()
        if self.path == "/oauth":
            return self._json(200, {"access_token": "tok", "expires_at": 4102444800000})
        body = json.loads(raw)
        Fake.bodies.append(body)
        assert self.headers["Authorization"] == "Bearer tok"
        assert body["function_call"] == "auto" and "functions" not in body  # text2image — встроенная функция
        content = "Не могу нарисовать такое." if Fake.refuse else f'Вот изображение <img src="{FILE_ID}" fuse="true"/>'
        self._json(200, {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})

    def do_GET(self):
        if self.path == f"/v1/files/{FILE_ID}/content":
            assert self.headers["Accept"] == "application/jpg"
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            self.wfile.write(JPEG)
            return
        self._json(404, {})


class GigaChatText2Image(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        port = cls.srv.server_address[1]
        cls.env = mock.patch.dict(os.environ, {
            "GIGACHAT_AUTH_KEY": "a2V5", "GIGACHAT_MIN_INTERVAL": "0", "GIGACHAT_MAX_RETRIES": "0",
            "GIGACHAT_OAUTH_URL": f"http://127.0.0.1:{port}/oauth", "GIGACHAT_BASE_URL": f"http://127.0.0.1:{port}/v1"})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.srv.shutdown()

    def test_draws_and_downloads_file(self):
        Fake.refuse = False
        data, mime = GigaChatImages().generate(build_prompt("Чашка кофе в осеннем парке", "STORY"), "STORY")
        self.assertEqual((data, mime), (JPEG, "image/jpeg"))
        sent = Fake.bodies[-1]["messages"][-1]["content"]
        self.assertTrue(sent.startswith("Нарисуй: Чашка кофе"))
        self.assertIn("9:16", sent)
        self.assertIn("Без текста", sent)

    def test_refusal_is_reported(self):
        Fake.refuse = True
        with self.assertRaises(ImageUnavailable) as e:
            GigaChatImages().generate("что-то", "PROMO")
        self.assertIn("не нарисовал", str(e.exception))


class Demo(unittest.TestCase):
    def test_png_has_format_aspect(self):
        for fmt, size in (("STORY", (270, 480)), ("SMART_BANNER", (360, 360)), ("PROMO", (480, 240))):
            data, mime = DemoImages().generate("осенний парк", fmt)
            self.assertEqual(mime, "image/png")
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            w, h = struct.unpack(">II", data[16:24])
            self.assertEqual((w, h), size)
            idat_len = struct.unpack(">I", data[33:37])[0]
            self.assertEqual(len(zlib.decompress(data[41:41 + idat_len])), h * (1 + w * 3))

    def test_deterministic_by_prompt(self):
        a = DemoImages().generate("вклад", "PROMO")[0]
        self.assertEqual(a, DemoImages().generate("вклад", "PROMO")[0])
        self.assertNotEqual(a, DemoImages().generate("кэшбэк", "PROMO")[0])


class Provider(unittest.TestCase):
    def test_choice_follows_llm_provider(self):
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "gigachat", "GIGACHAT_AUTH_KEY": "a2V5", "IMAGE_PROVIDER": ""}):
            self.assertEqual(images.from_env().name, "gigachat")
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "openai", "LLM_API_KEY": "", "IMAGE_API_KEY": "", "IMAGE_PROVIDER": ""}):
            self.assertEqual(images.from_env().name, "off")
        with mock.patch.dict(os.environ, {"IMAGE_PROVIDER": "demo"}):
            self.assertEqual(images.from_env().name, "demo")

    def test_rejects_non_images(self):
        with self.assertRaises(ImageUnavailable):
            images.sniff(b"<html><script>")

    def test_prompt_keeps_palette_and_rules(self):
        p = build_prompt("Самолёт над морем.", "SMART_BANNER", "#E8FAFFFF")
        self.assertIn("#E8FAFF", p)
        self.assertIn("без логотипов", p)
        self.assertIn("квадратная", p)


if __name__ == "__main__":
    unittest.main()
