# Данные

`mock/` — синтетический датасет заказчика. В присланном архиве было 11 из 18 файлов; недостающие восстановлены по `docs/mock-data.md` и `docs/task.md`.

| Файл | Источник |
| --- | --- |
| `banner_types.json`, `channels.json`, `campaigns.json`, `campaign_*.json`, `cbro_export.json` | оригинал заказчика |
| `segments.json`, `places.json`, `tags.json`, `segment_types.json` | восстановлены из таблиц `mock-data.md` §1 — значения совпадают |
| `topics.json` | коды из `mock-data.md` §1.1; подписи SALES, RECOMMENDATION, LIFESTYLE, ADVICES, COURSES, EVENT — из `campaign_create_payloads.json`, остальные придуманы |
| `validation_rules.json` | **реконструкция**: оригинал (43 ошибки, 3 warning) не прислан. Коды из ТЗ сохранены, остальные добавлены командой |
| `lifecycle_transitions.json` | **реконструкция**: журнал переходов собран по статусам кампаний; комментарий decline у 104 — из `mock-data.md` §5, у 115 — придуман |

Как только организаторы пришлют полный архив, оригиналы нужно положить поверх — код читает файлы по тем же именам. После замены `validation_rules.json` прогоните `go test ./...` в `api/`: тесты сверяют коды.
