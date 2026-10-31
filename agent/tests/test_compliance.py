"""Блок отказов по закону о рекламе и скрытая памятка к каждому сообщению."""
import os
import unittest

from app import agent as A
from app.api_client import ApiClient
from app.compliance import check_creative, check_message


class Spy:
    def __init__(self):
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(messages)
        return {"content": "Понял, давайте уточним детали.", "tool_calls": []}


class Compliance(unittest.TestCase):
    def setUp(self):
        os.environ["SESSIONS_FILE"] = ""
        A.SESSIONS.clear()

    def test_stop_topics(self):
        for text in ["Сделай рекламу онлайн-казино для клиентов 18–25", "Промо вейпов со скидкой", "кампания для криптобиржи",
                     "реклама водки к Новому году", "Продвигаем букмекера: ставки на спорт"]:
            self.assertIsNotNone(check_message(text), text)

    def test_legit_bank_briefs_pass(self):
        for text in ["Кампания по вкладу для клиентов 26–45 в Москве и СПб, промо на главном, ставка 16%, с 5 ноября до конца года",
                     "Почему «Ипотека: ставка 4,9%» на доработке?", "Можно ли запустить «Сомелье: подбор вина»?",
                     "Вооружитесь кэшбэком на всё", "Кредитная карта с льготным периодом"]:
            self.assertIsNone(check_message(text), text)

    def test_creative_rules(self):
        self.assertTrue(check_creative({"content": {"title": "Лучший банк страны", "text": "Откройте вклад"}}))
        self.assertTrue(check_creative({"content": {"title": "Кредит без отказа", "text": "Одобрим всем"}}))
        self.assertFalse(check_creative({"content": {"title": "Вклад под 16%", "text": "Откройте вклад за пару минут",
                                                      "link": {"iOS": "mobilebank://casino"}}}))  # ссылки не проверяем

    def test_refusal_without_model_and_hidden_turn_prompt(self):
        spy = Spy()
        a = A.Agent(ApiClient("http://127.0.0.1:9"), spy)
        st = a.chat(None, "Запусти рекламу сигарет на главном экране", "ivanov.p", "campaignManager")
        self.assertIn("нарушает законодательство РФ", st["reply"])
        self.assertEqual(spy.seen, [])  # модель не вызывалась

        st = a.chat(st["session_id"], "Хорошо, тогда кампания по вкладу")
        sent_user = [m for m in spy.seen[-1] if m["role"] == "user"][-1]["content"]
        self.assertIn("Служебная памятка", sent_user)  # памятка ушла модели вместе с сообщением
        # …но не попала ни в историю, ни в ленту для фронта
        s = A.SESSIONS[st["session_id"]]
        self.assertFalse(any("Служебная памятка" in (m.get("content") or "") for m in s.messages))
        self.assertFalse(any("Служебная памятка" in (t.get("text") or "") for t in st["transcript"]))


if __name__ == "__main__":
    unittest.main()
