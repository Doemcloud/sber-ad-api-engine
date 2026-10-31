"""Сквозные сценарии из task.md §8–9 на настоящем Go API и моках заказчика.
Модель заменена скриптом (ScriptedLLM), всё остальное — боевой код агента.

Запуск: python -m unittest discover -s tests   (из папки agent/)
API поднимается автоматически из ../api (нужен Go) либо берётся из API_URL.
WRITE_DIALOGS=1 — записать стенограммы в docs/dialogs/.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from app import agent as agent_mod
from app.agent import Agent
from app.api_client import ApiClient
from tests.scripted_llm import ScriptedLLM, call, calls, say

ROOT = Path(__file__).resolve().parents[2]
_proc = None


def setUpModule():
    global _proc
    if os.getenv("API_URL"):
        return
    tmp = tempfile.mkdtemp()
    binary = os.path.join(tmp, "api")
    subprocess.run(["go", "build", "-o", binary, "./cmd/server"], cwd=ROOT / "api", check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PORT": str(port), "MOCK_DIR": str(ROOT / "data" / "mock"), "STATE_FILE": os.path.join(tmp, "state.json")}
    _proc = subprocess.Popen([binary], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ["API_URL"] = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(os.environ["API_URL"] + "/health", timeout=1)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("API не поднялся")


def tearDownModule():
    if _proc:
        _proc.terminate()


class Transcript:
    def __init__(self, title: str):
        self.lines = [f"# {title}", "", "_Воспроизводимый диалог: настоящий агент и API на данных заказчика, ответы модели заданы скриптом (tests/test_scenarios.py)._", ""]

    def user(self, who: str, text: str):
        self.lines += [f"**{who}:** {text}", ""]

    def agent(self, st: dict):
        if st.get("reply"):
            self.lines += [f"**Ассистент:** {st['reply']}", ""]
        p = st.get("pending_action")
        if p:
            self.lines += ["> **Ассистент предлагает (нужно подтверждение):**"] + [f"> {s['n']}. {s['summary']}" for s in p["steps"]] + [""]
        for r in st.get("last_result") or []:
            pass

    def confirm(self, st: dict):
        self.lines += ["_Менеджер нажимает «Подтвердить»._", ""]
        res = st.get("last_result") or []
        self.lines += ["> **Выполнено:** " + "; ".join(("✓ " if r["ok"] else "✗ ") + r["summary"] for r in res), ""]
        if st.get("campaign"):
            c = st["campaign"]
            v = st.get("validation") or {}
            label = {"DRAFT": "черновик", "ON_MODERATION": "на модерации", "NEEDS_WORK": "на доработке", "APPROVED": "одобрена", "ACTIVE": "запущена"}.get(c["state"], c["state"])
            self.lines += [f"> Кампания «{c['name']}»: {label}, ошибок {len(v.get('errors', []))}, замечаний {len(v.get('warnings', []))}", ""]
        self.agent({"reply": st.get("reply")})

    def save(self, name: str):
        if os.getenv("WRITE_DIALOGS"):
            out = ROOT / "docs" / "dialogs"
            out.mkdir(parents=True, exist_ok=True)
            (out / name).write_text("\n".join(self.lines), encoding="utf-8")


def tool_results(llm: ScriptedLLM) -> list[dict]:
    return llm.last_tool_results()


class Scenarios(unittest.TestCase):
    def setUp(self):
        agent_mod.SESSIONS.clear()

    def make(self, script):
        llm = ScriptedLLM(script)
        return Agent(ApiClient(), llm), llm

    # ---------------- Диалог 1: бриф → кампания → модерация (task.md §9)
    def test_brief_to_moderation(self):
        t = Transcript("Диалог 1. Бриф → кампания → модерация")
        long_title = "Вклад под 16% годовых до конца года для жителей Москвы и Санкт-Петербурга — откройте онлайн за пару минут без визита"
        story = {"title": "Вклад под 16% до конца года", "text": "Откройте вклад в приложении за пару минут",
                 "titleStyle": {"fontSize": 28, "fontWeight": "bold", "textColor": "#FFFFFFFF"},
                 "background": {"color": "#21A038FF"}, "image": {"url": "https://picsum.photos/seed/deposit/600/900"},
                 "buttonName": "Подробнее", "actionType": "default", "voiceOver": "Вклад под 16 процентов"}
        promo = {"role": "promo", "component": {"role": "linearContainer", "axis": "v", "style": {"backgroundColor": "#FFFFFFFF"}, "components": [
            {"role": "image", "url": "https://picsum.photos/seed/deposit2/800/400", "aspectRatio": 2.0},
            {"role": "text", "format": "html", "text": "<b>16% годовых</b> до 31 декабря"},
            {"role": "text", "format": "none", "text": "Вклад открывается онлайн, пополнение и снятие — в приложении"},
            {"role": "button", "text": "Открыть вклад", "actionType": "openSmartLink", "link": {"iOS": "mobilebank://deposits/new", "android": "mobilebank://deposits/new"}}]}}
        campaign = {"name": "Вклад 16%: до конца года", "marketingName": "Вклад под 16%", "startDate": "2026-11-05", "startTime": "00:00",
                    "endDate": "2026-12-31", "endTime": "23:59", "topic": "SALES", "tags": [5], "keywords": "вклад;ставка;16%",
                    "audienceType": "SEGMENTED", "weight": 0, "initialCtr": 15, "places": [1]}
        a, llm = self.make([
            calls(call("get_places"), call("get_segments"), call("get_tags"), call("get_topics")),
            say("Понял: продвигаем вклад под 16%, показы с 5 ноября до 31 декабря 2026, тематика «Продажи». "
                "Аудитория — таргетинг по сегментам «Возраст 26–45» (24 млн), «Москва» (13 млн), «Санкт-Петербург» (5,6 млн); "
                "клиент попадает в аудиторию, если входит хотя бы в один сегмент. Исключаем тех, кто отписался от рекламы.\n\n"
                "Уточню два момента:\n1) «Промо на главном» — это сторис в промо-блоке главного экрана или смарт-баннер на главном? Предлагаю сторис.\n"
                "2) Добавить тег «Вклад»? Без тегов кампанию сложнее найти в отчётах."),
            calls(call("validate_banner", bannerTypeId=1, content={**story, "title": long_title})),
            calls(call("create_campaign", campaign=campaign, ref="camp"),
                  call("set_segments", campaign_id="$camp", included=["AGE_26_45", "CITY_MSK", "CITY_SPB"], excluded=["EXC_UNSUBSCRIBED"]),
                  call("create_banner", campaign_id="$camp", name="Сторис: вклад 16%", bannerTypeId=1, content=story, ref="banner1"),
                  call("create_content", campaign_id="$camp", name="Промо-экран: вклад 16%", content=promo, ref="content1"),
                  call("create_creative", campaign_id="$camp", name="Сторис iOS", bannerId="$banner1", contentId="$content1", channelCode="iOS"),
                  call("create_creative", campaign_id="$camp", name="Сторис Android", bannerId="$banner1", contentId="$content1", channelCode="ANDROID"),
                  call("create_creative", campaign_id="$camp", name="Сторис Web", bannerId="$banner1", channelCode="WEB")),
            say("Подготовил кампанию «Вклад 16%: до конца года»: сторис в промо-блоке главного экрана, тег «Вклад», обычный приоритет показа. "
                "Сторис «Вклад под 16% до конца года» ведёт на промо-экран с кнопкой «Открыть вклад»; размещаем в iOS и Android — "
                "в веб-версии сторис не показываются. Заголовок первого варианта не помещался в формат, я его сократил. Проверьте и подтвердите."),
        ])
        t.user("Менеджер", "Кампания по вкладу для клиентов 26–45 в Москве и СПб, промо на главном, ставка 16%, с 5 ноября до конца года")
        st = a.chat(None, "Кампания по вкладу для клиентов 26–45 в Москве и СПб, промо на главном, ставка 16%, с 5 ноября до конца года")
        t.agent(st)
        sid = st["session_id"]
        self.assertIsNone(st["pending_action"])

        t.user("Менеджер", "Сторис, тег добавь, аудитория норм")
        st = a.chat(sid, "Сторис, тег добавь, аудитория норм")
        # слишком длинный заголовок и STORY в WEB отсекаются проверками агента до API
        rejected = [r for msgs in llm.seen for m in msgs if m["role"] == "tool" for r in [json.loads(m["content"])] if isinstance(r, dict) and r.get("ok") is False]
        codes = {e["code"] for r in rejected for e in r["errors"]}
        self.assertIn("BANNER_TITLE_TOO_LONG", codes)
        self.assertIn("CREATIVE_CHANNEL_NOT_ALLOWED", codes)
        t.agent(st)
        plan = st["pending_action"]
        self.assertEqual(len(plan["steps"]), 6)

        a.llm.responses += [say("Готово: кампания сохранена как черновик, ошибок и замечаний нет. Отправить на модерацию?")]
        st = a.confirm(sid, plan["id"], True)
        t.confirm(st)
        cid = st["campaign"]["id"]
        self.assertEqual(st["campaign"]["state"], "DRAFT")
        self.assertEqual(st["validation"]["errors"], [])
        self.assertEqual(st["validation"]["warnings"], [])
        self.assertEqual(len(st["campaign"]["creatives"]), 2)

        a.llm.responses += [calls(call("to_moderation", campaign_id=cid)), say("Отправляю на модерацию — подтвердите."),
                            say("Кампания на модерации. Модератор одобрит её или вернёт на доработку с комментарием; после одобрения её можно будет запустить — тогда реклама появится в приложении.")]
        t.user("Менеджер", "Да, отправляй")
        st = a.chat(sid, "Да, отправляй")
        t.agent(st)
        st = a.confirm(sid, st["pending_action"]["id"], True)
        t.confirm(st)
        self.assertEqual(st["campaign"]["state"], "ON_MODERATION")

        audit = ApiClient().get(f"/campaigns/{cid}/audit")
        self.assertEqual([x["action"] for x in audit if x["entity"] == "CAMPAIGN"], ["CREATE", "TO_MODERATION"])
        self.assertTrue(all(x["actor"] == "ivanov.p" for x in audit))
        t.save("01-brief-to-moderation.md")

    # ---------------- Диалог 2: правка отклонённой кампании 104
    def test_fix_declined_104(self):
        t = Transcript("Диалог 2. Правка отклонённой кампании")
        story = {"title": "Ипотека от 4,9%", "text": "Узнайте условия и подайте заявку онлайн", "actionType": "default",
                 "background": {"color": "#0B7A3EFF"}, "buttonName": "Подробнее"}
        a, llm = self.make([
            calls(call("get_campaign", campaign_id=104), call("get_warnings", campaign_id=104), call("get_audit", campaign_id=104)),
            say("Кампанию вернула на доработку Мария Петрова 22 октября: «Креативы настроены не для всех мест показа; добавьте теги кампании». "
                "Сейчас три замечания: нет креатива для промо-блока на главном экране, архивный сторис-слот отключён, нет тегов. "
                "Предлагаю: сделать сторис для iOS и Android, убрать отключённый слот, добавить тег «Банковские продукты» и снова отправить на модерацию."),
            calls(call("update_campaign", campaign_id=104, campaign={"places": [1], "tags": [1]}),
                  call("create_banner", campaign_id=104, name="Сторис: ипотека", bannerTypeId=1, content=story, ref="b"),
                  call("create_creative", campaign_id=104, name="Ипотека iOS", bannerId="$b", channelCode="iOS"),
                  call("create_creative", campaign_id=104, name="Ипотека Android", bannerId="$b", channelCode="ANDROID"),
                  call("to_moderation", campaign_id=104)),
            say("Подготовил правки: места размещения и теги, сторис и размещение на двух платформах, затем повторная отправка. Кампанию на доработке можно менять."),
            say("Готово: замечания исправлены, кампания снова на модерации, замечаний нет."),
        ])
        t.user("Менеджер", "Почему «Ипотека: ставка 4,9%» на доработке?")
        st = a.chat(None, "Почему «Ипотека: ставка 4,9%» на доработке?")
        t.agent(st)
        audit = [r for r in tool_results(llm) if isinstance(r, list)]
        self.assertTrue(any(e.get("comment") for e in audit[0]))
        t.user("Менеджер", "Да, исправляй всё и отправляй")
        st = a.chat(st["session_id"], "Да, исправляй всё и отправляй")
        t.agent(st)
        self.assertEqual(len(st["pending_action"]["steps"]), 5)
        st = a.confirm(st["session_id"], st["pending_action"]["id"], True)
        t.confirm(st)
        self.assertEqual(st["campaign"]["state"], "ON_MODERATION")
        self.assertEqual(st["validation"]["warnings"], [])
        t.save("02-fix-declined-campaign.md")

    # ---------------- Диалог 3: объяснение запретов жизненного цикла
    def test_lifecycle_explanations(self):
        t = Transcript("Диалог 3. Почему нельзя активировать или удалить")
        a, llm = self.make([
            calls(call("activate", campaign_id=103)),
            say("Готовлю запуск кампании — подтвердите."),
            say("Запустить пока нельзя: кампания на модерации, а запускать можно только одобренную. Дождитесь решения модератора — я подскажу, когда можно будет запускать."),
            calls(call("approve", campaign_id=103)),
            say("Одобряет только модератор — менеджер не может одобрить свою кампанию. Это защита от ошибок: кампанию всегда проверяет второй человек."),
            calls(call("delete_campaign", campaign_id=102)),
            say("Готовлю удаление кампании — подтвердите."),
            say("Удалить нельзя: кампания уже показывается клиентам. Можно остановить показы, но учтите — запустить её снова не получится, она останется в истории."),
        ])
        t.user("Менеджер", "Активируй «Сомелье: подбор вина»")
        st = a.chat(None, "Активируй «Сомелье: подбор вина»")
        t.agent(st)
        sid = st["session_id"]
        st = a.confirm(sid, st["pending_action"]["id"], True)
        t.confirm(st)
        self.assertEqual(st["last_result"][0]["errors"][0]["code"], "ACTIVATE_NOT_ALLOWED")
        self.assertIn("hint", st["last_result"][0]["errors"][0])

        t.user("Менеджер", "Тогда одобри её сам")
        st = a.chat(sid, "Тогда одобри её сам")
        t.agent(st)
        self.assertIsNone(st["pending_action"])
        self.assertEqual(tool_results(llm)[-1]["errors"][0]["code"], "ROLE_FORBIDDEN")

        t.user("Менеджер", "Удали «Кэшбэк за автоплатежи»")
        st = a.chat(sid, "Удали «Кэшбэк за автоплатежи»")
        t.agent(st)
        st = a.confirm(sid, st["pending_action"]["id"], True)
        t.confirm(st)
        self.assertEqual(st["last_result"][0]["errors"][0]["code"], "DELETE_NOT_ALLOWED")
        t.save("03-lifecycle-explanations.md")

    # ---------------- Модератор в ассистенте + отказ от плана
    def test_moderator_and_rejected_plan(self):
        a, llm = self.make([
            calls(call("decline", campaign_id=110, comment="")),
            say("Нужен комментарий — что исправить менеджеру?"),
            calls(call("decline", campaign_id=110, comment="Нет креатива для depositScreenPromo")),
            say("Готов вернуть на доработку — подтвердите."),
            calls(call("decline", campaign_id=110, comment="Нет креатива для промо-экрана вклада; добавьте теги")),
            say("Исправил комментарий — подтвердите."),
        ])
        st = a.chat(None, "Отклони 110", user="petrova.m", role="campaignModerator")
        self.assertEqual(tool_results(llm)[-1]["errors"][0]["code"], "DECLINE_COMMENT_REQUIRED")
        st = a.chat(st["session_id"], "Нет креатива для depositScreenPromo")
        st = a.confirm(st["session_id"], st["pending_action"]["id"], False)
        self.assertEqual(ApiClient().get("/campaigns/110")["state"], "ON_MODERATION")  # ничего не записано
        # «Отменить» без причины: ассистент спрашивает, что не так, и ждёт — модель не вызывается
        self.assertIn("Что не так", st["reply"])
        self.assertTrue(st["awaiting_fix"])
        self.assertIsNone(st["pending_action"])
        # ответ менеджера — причина отмены: модель получает её вместе с отменённым планом и пересобирает план
        st = a.chat(st["session_id"], "Комментарий слишком короткий, добавь про теги")
        sent = [m for m in llm.seen[-2] if m["role"] == "user"][-1]["content"]
        self.assertIn("Причина отмены плана", sent)
        self.assertIn("добавь про теги", sent)
        self.assertFalse(st["awaiting_fix"])
        self.assertIn("теги", st["pending_action"]["steps"][0]["args"]["comment"])


if __name__ == "__main__":
    unittest.main()
