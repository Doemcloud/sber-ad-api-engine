# sber-ad-api-engine

SibКод, кейс 1 · команда SUPh. AI-конструктор рекламных кампаний для приложения, веба и веб-про Сбера: менеджер описывает кампанию словами, агент собирает сущность кампании по справочникам, дозапрашивает недостающее, генерирует креативы с предпросмотром и сохраняет всё в БД после подтверждения.

## Запуск

```bash
cp .env.example .env        # вписать LLM_API_KEY (подходит любая OpenAI-совместимая LLM)
docker compose up --build
```

- Интерфейс: http://localhost:3000
- AI-агент: http://localhost:8000/docs
- API: http://localhost:8080/api/campaigns

Без ключа агент работает в mock-режиме: отвечает списком недостающих полей, чтобы фронт мог интегрироваться заранее.

Локально без Docker:

```bash
cd api && SEED_DIR=../data/mock go run ./cmd/server
cd agent && pip install -r requirements.txt && API_URL=http://localhost:8080 uvicorn app.main:app --reload
cd web && npm install && npm run dev
```

## Архитектура

```
web (React+TS) ──chat/confirm──▶ agent (Python, tool calling) ──REST──▶ api (Go) ──▶ store (JSON → Postgres)
      └──────────── список и редактирование кампаний ───────────────────▶ api
```

Правила, которые держит код, а не промпт:
- решение «хватает ли данных» принимает Go API (`POST /api/campaigns/validate`);
- агент пишет в БД только через pending action, который менеджер подтверждает кнопкой (`POST /confirm`);
- сегменты, места показа и рекламодатели берутся только из справочников, а недостающие создаются после подтверждения.

## Структура и владельцы

| Папка | Что внутри | Владелец |
| --- | --- | --- |
| `web/` | Чат, карточка кампании, предпросмотр, список и редактирование кампаний | JS / Frontend |
| `agent/` | Системный промпт, tools, генерация креативов, автопроверка | Python / AI Agent |
| `api/` | REST, валидация сущности, статусы, хранилище | Go / Backend |
| `data/mock/` | Справочники и mock-кампании | DevOps / Data |
| `contracts/` | `campaign.schema.json` — общий контракт сущности | все |
| `docker-compose.yml`, `.env.example` | Запуск и связка сервисов | DevOps / Infra |

## API (Go)

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/api/segments`, `/api/placements`, `/api/advertisers` | Справочники |
| POST | `/api/segments`, `/api/advertisers` | Создать запись справочника |
| GET | `/api/campaigns?status=&placement_id=&advertiser_id=&segment_id=&q=` | Поиск кампаний |
| GET | `/api/campaigns/{id}` | Кампания |
| POST | `/api/campaigns` | Создать (сохраняется и неполный черновик со статусом `needs_info`) |
| PUT | `/api/campaigns/{id}` | Изменить (patch-слияние) |
| POST | `/api/campaigns/{id}/status` | Сменить статус по разрешённым переходам |
| POST | `/api/campaigns/validate` | Проверить черновик: `missing`, `problems` |

## Agent (Python)

| Метод | Путь | Ответ |
| --- | --- | --- |
| POST | `/chat` `{session_id?, message}` | `{session_id, reply, draft, missing, pending_actions}` |
| POST | `/confirm` `{session_id, action_id, approved}` | то же |
| GET | `/sessions/{id}` | текущее состояние |

Tools агента: `get_reference`, `update_draft`, `find_campaigns`, `propose_segment`, `propose_advertiser`, `generate_creatives`, `propose_save`.

## TODO

- [ ] Сверить `contracts/campaign.schema.json` и mock-данные с доменной моделью заказчика (Data + Backend).
- [ ] Подключить LLM и генерацию изображений, отладить промпт на демо-сценарии «кофейня Зерно» (AI).
- [ ] Хранилище: JSON-файлы → Postgres, если нужна настоящая СУБД (Backend + Infra).
- [ ] Защита от prompt injection, расширенный список запрещённых формулировок.
- [ ] Цифры статистики для презентации (придуманные, в `data/mock/campaigns.json`).
