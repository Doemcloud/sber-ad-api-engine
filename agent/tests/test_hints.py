"""Подсказки: варианты ответа из реплики модели, следующие шаги, рекомендации по кампании."""
import os
import unittest

from app import agent as A
from app.api_client import ApiClient
from app.hints import extract_choices, next_steps, recommendations

DICTS = {
    "segments": [{"code": "EXC_UNSUBSCRIBED", "name": "Исключение. Отписались от рекламы", "count": 15_000_000},
                 {"code": "CITY_SLD", "name": "Сочи", "count": 400_000}],
    "banner_types": [{"id": 1, "code": "STORY", "channels": ["iOS", "ANDROID"]},
                     {"id": 2, "code": "SMART_BANNER", "channels": ["iOS", "ANDROID", "WEB"]}],
}


def campaign(**kw):
    c = {"id": 116, "name": "Вклад 16%", "state": "DRAFT", "audienceType": "SEGMENTED", "endDate": "2026-12-31",
         "segments": {"included": ["CITY_SLD"], "excluded": []},
         "banners": [{"id": 217, "name": "Сторис", "bannerTypeId": 1}], "contents": [],
         "creatives": [{"bannerId": 217, "channelCode": "iOS"}]}
    c.update(kw)
    return c


class Asks:
    def complete(self, messages, tools):
        return {"content": "Какой формат на главном?\nВарианты: Сторис | Смарт-баннер | Оба", "tool_calls": []}


class Hints(unittest.TestCase):
    def test_choices_line_becomes_buttons_and_is_hidden(self):
        os.environ["SESSIONS_FILE"] = ""
        a = A.Agent(ApiClient("http://127.0.0.1:9"), Asks())
        st = a.chat(None, "Кампания по вкладу", "ivanov.p", "campaignManager")
        self.assertEqual(st["reply"], "Какой формат на главном?")
        self.assertEqual(st["suggestions"], ["Сторис", "Смарт-баннер", "Оба"])
        self.assertNotIn("Варианты", st["transcript"][-1]["text"])
        self.assertNotIn("Варианты", A.SESSIONS[st["session_id"]].messages[-1]["content"])  # и в истории модели

    def test_recommendations(self):
        recs = recommendations(campaign(), {"warningDetails": [{"code": "TAGS_MISSING"}], "errors": []}, DICTS, "campaignManager")
        ids = [r["id"] for r in recs]
        self.assertIn("unsub", ids)              # не исключены отписавшиеся
        self.assertIn("narrow", ids)             # 400 тыс. — узкая аудитория
        self.assertTrue(any(i.startswith("platform-217-ANDROID") for i in ids))  # сторис только на iOS
        self.assertTrue(all("«Вклад 16%»" in r["prompt"] for r in recs))
        self.assertLessEqual(len(recs), 4)
        self.assertEqual(recommendations(campaign(), None, DICTS, "campaignModerator"), [])
        self.assertEqual(recommendations(campaign(state="STOPPED"), None, DICTS, "campaignManager")[0]["id"], "resume")
        self.assertEqual(recommendations(campaign(state="ON_MODERATION"), None, DICTS, "campaignManager"), [])

    def test_next_steps(self):
        self.assertEqual(next_steps(True, False, campaign(), None, "campaignManager"), [])  # план ждёт кнопок
        self.assertIn("Поменяй даты", next_steps(False, True, None, None, "campaignManager"))
        self.assertEqual(next_steps(False, False, campaign(state="APPROVED"), None, "campaignManager")[0], "Запусти кампанию")
        self.assertEqual(next_steps(False, False, campaign(state="NEEDS_WORK"), {"errors": []}, "campaignManager")[:2],
                         ["Исправь замечания модератора", "Отправь на модерацию"])

    def test_extract_variants(self):
        self.assertEqual(extract_choices("Да?\n**Варианты:** Да; Нет")[1], ["Да", "Нет"])
        self.assertEqual(extract_choices("Без вариантов")[1], [])
        self.assertEqual(extract_choices("?\nВарианты: Сторис и тег «Вклад» | «Смарт-баннер» | Оба.")[1],
                         ["Сторис и тег «Вклад»", "Смарт-баннер", "Оба"])


if __name__ == "__main__":
    unittest.main()
