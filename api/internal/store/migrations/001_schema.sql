-- Схема БД рекламных кампаний по доменной модели ТЗ (task.md §2).
-- Целевая СУБД — Platform V Pangolin DB (СберТех, на основе PostgreSQL);
-- скрипт использует только стандартный SQL PostgreSQL и выполняется в Pangolin без изменений.
-- Идемпотентен: можно применять повторно.

-- ---------- справочники (§2.9) ----------
CREATE TABLE IF NOT EXISTS topic (
    value       varchar(64)  PRIMARY KEY,
    label       varchar(255) NOT NULL
);
COMMENT ON TABLE topic IS 'TOPIC: тематики кампаний (фиксированный список)';

CREATE TABLE IF NOT EXISTS tag (
    id          bigint       PRIMARY KEY,
    name        varchar(255) NOT NULL UNIQUE
);
COMMENT ON TABLE tag IS 'TAG: теги кампаний; менеджер может создавать новые (POST /tags)';

CREATE TABLE IF NOT EXISTS channel (
    id          bigint       PRIMARY KEY,
    code        varchar(32)  NOT NULL UNIQUE,
    description varchar(255) NOT NULL
);
COMMENT ON TABLE channel IS 'CHANNEL: платформы показа — iOS, ANDROID, WEB';

CREATE TABLE IF NOT EXISTS banner_type (
    id               bigint       PRIMARY KEY,
    code             varchar(32)  NOT NULL UNIQUE,
    description      varchar(255) NOT NULL,
    preview_form     varchar(64)  NOT NULL DEFAULT '',
    title_max_length int          NOT NULL CHECK (title_max_length > 0),
    text_max_length  int          NOT NULL CHECK (text_max_length > 0),
    channels         varchar(32)[] NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE banner_type IS 'BANNER_TYPE: STORY (id 1), SMART_BANNER (id 2) — лимиты длины и допустимые каналы';

CREATE TABLE IF NOT EXISTS segment_type (
    code        varchar(64)  PRIMARY KEY,
    name        varchar(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS segment (
    code        varchar(64)  PRIMARY KEY,
    name        varchar(255) NOT NULL,
    type        varchar(64)  NOT NULL REFERENCES segment_type(code),
    state       varchar(16)  NOT NULL CHECK (state IN ('NEW', 'ACTIVE', 'ARCHIVED')),
    count       bigint       NOT NULL DEFAULT 0 CHECK (count >= 0)
);
COMMENT ON TABLE segment IS 'SEGMENT: сегменты аудитории; создаются в системе аудиторий банка, здесь — только выбор';

CREATE TABLE IF NOT EXISTS place (
    id             bigint       PRIMARY KEY,
    code           varchar(128) NOT NULL UNIQUE,
    description    varchar(255) NOT NULL,
    default_banner varchar(32)  REFERENCES banner_type(code),
    state          varchar(16)  NOT NULL CHECK (state IN ('ACTIVE', 'INACTIVE'))
);
COMMENT ON TABLE place IS 'PLACE: места показа в приложении; defaultBanner — формат баннера места';

-- ---------- кампания и дочерние сущности (§2.2–2.8) ----------
CREATE TABLE IF NOT EXISTS campaign (
    id               bigint        PRIMARY KEY,
    name             varchar(100)  NOT NULL UNIQUE,
    marketing_name   varchar(255),
    start_date       date          NOT NULL,
    start_time       varchar(5)    NOT NULL CHECK (start_time ~ '^[0-2][0-9]:[0-5][0-9]$'),
    end_date         date,
    end_time         varchar(5)    CHECK (end_time IS NULL OR end_time ~ '^[0-2][0-9]:[0-5][0-9]$'),
    topic            varchar(64)   NOT NULL REFERENCES topic(value),
    keywords         text,
    audience_type    varchar(16)   NOT NULL CHECK (audience_type IN ('ALL_USERS', 'SEGMENTED')),
    weight           numeric(10,2) NOT NULL DEFAULT 0 CHECK (weight >= 0),
    initial_ctr      numeric(5,2)  NOT NULL DEFAULT 15 CHECK (initial_ctr BETWEEN 0 AND 100),
    state            varchar(16)   NOT NULL CHECK (state IN ('DRAFT', 'ON_MODERATION', 'NEEDS_WORK', 'APPROVED', 'ACTIVE', 'ACTIVE_EDITING', 'STOPPED', 'ARCHIVED')),
    published        boolean       NOT NULL DEFAULT false,
    author           varchar(64)   NOT NULL DEFAULT '',
    last_edit_author varchar(64)   NOT NULL DEFAULT '',
    CHECK (end_time IS NULL OR end_date IS NOT NULL)
);
COMMENT ON TABLE campaign IS 'CAMPAIGN: шапка кампании, статус жизненного цикла и флаг published (идёт показ)';
CREATE INDEX IF NOT EXISTS campaign_state_idx ON campaign(state);

CREATE TABLE IF NOT EXISTS campaign_tag (
    campaign_id bigint NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    tag_id      bigint NOT NULL REFERENCES tag(id),
    pos         int    NOT NULL DEFAULT 0,
    PRIMARY KEY (campaign_id, tag_id)
);

CREATE TABLE IF NOT EXISTS campaign_place (
    campaign_id bigint NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    place_id    bigint NOT NULL REFERENCES place(id),
    pos         int    NOT NULL DEFAULT 0,
    PRIMARY KEY (campaign_id, place_id)
);
COMMENT ON TABLE campaign_place IS 'CAMPAIGN N:M PLACE';

CREATE TABLE IF NOT EXISTS campaign_segment (
    campaign_id  bigint      NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    segment_code varchar(64) NOT NULL REFERENCES segment(code),
    kind         varchar(8)  NOT NULL CHECK (kind IN ('INCLUDED', 'EXCLUDED')),
    pos          int         NOT NULL DEFAULT 0,
    PRIMARY KEY (campaign_id, segment_code, kind)
);
COMMENT ON TABLE campaign_segment IS 'Аудитория: сегменты включения (объединяются по ИЛИ) и исключения';

CREATE TABLE IF NOT EXISTS banner (
    id             bigint       PRIMARY KEY,
    campaign_id    bigint       NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    name           varchar(255) NOT NULL,
    banner_type_id bigint       NOT NULL REFERENCES banner_type(id),
    content        jsonb        NOT NULL
);
COMMENT ON TABLE banner IS 'BANNER: один JSON-контент (заголовок, текст, стили, кнопка, действие)';

CREATE TABLE IF NOT EXISTS content (
    id           bigint       PRIMARY KEY,
    campaign_id  bigint       NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    name         varchar(255) NOT NULL,
    content_type varchar(16)  NOT NULL CHECK (content_type IN ('PROMO')),
    content      jsonb        NOT NULL
);
COMMENT ON TABLE content IS 'CONTENT: документ PROMO-экрана (до 6 компонентов)';

CREATE TABLE IF NOT EXISTS creative (
    id           bigint       PRIMARY KEY,
    campaign_id  bigint       NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    name         varchar(255) NOT NULL,
    banner_id    bigint       NOT NULL REFERENCES banner(id) ON DELETE CASCADE,
    content_id   bigint       REFERENCES content(id) ON DELETE SET NULL,
    channel_code varchar(32)  NOT NULL REFERENCES channel(code),
    UNIQUE (banner_id, channel_code)
);
COMMENT ON TABLE creative IS 'CREATIVE: баннер + промо-экран (необязательно) + канал';

-- ---------- аудит (§6.3, mocks/lifecycle_transitions.json) ----------
CREATE TABLE IF NOT EXISTS lifecycle_transitions (
    id          bigint       PRIMARY KEY,
    campaign_id bigint       NOT NULL,           -- без FK: история остаётся после удаления кампании
    entity      varchar(32)  NOT NULL,
    entity_id   bigint       NOT NULL,
    action      varchar(32)  NOT NULL,
    changes     jsonb,
    at          timestamp    NOT NULL,
    actor       varchar(64)  NOT NULL,
    comment     text
);
COMMENT ON TABLE lifecycle_transitions IS 'Серверный аудит: все пишущие операции и переходы ЖЦ — кто, когда, что изменил';
CREATE INDEX IF NOT EXISTS lifecycle_transitions_campaign_idx ON lifecycle_transitions(campaign_id, id);

-- ---------- служебное ----------
CREATE TABLE IF NOT EXISTS id_sequence (
    kind    varchar(32) PRIMARY KEY,
    next_id bigint      NOT NULL
);
COMMENT ON TABLE id_sequence IS 'Следующие id по видам сущностей (кампании 1xx, баннеры 2xx, контент 3xx, креативы 4xx — как в моках)';
