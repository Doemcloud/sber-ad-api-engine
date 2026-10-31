-- Изображения креативов, созданные нейрогенерацией (агент) или загруженные вручную.
-- Отдаются по GET /media/{id}; ссылка вида {PUBLIC_URL}/media/{id} кладётся в image.url баннера и PROMO.
CREATE TABLE IF NOT EXISTS media (
    id          uuid PRIMARY KEY,
    mime        text        NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp')),
    data        bytea       NOT NULL,
    prompt      text,
    author      text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS media_author_idx ON media (author, created_at DESC);
