-- ranges es la fuente de verdad (datos crudos, nunca se borran por lógica de negocio)
-- positions es derivado y recalculable

CREATE TABLE IF NOT EXISTS anchors (
    id          TEXT PRIMARY KEY,
    x           DOUBLE PRECISION NOT NULL, -- metros, medido con cinta métrica
    y           DOUBLE PRECISION NOT NULL,
    z           DOUBLE PRECISION NOT NULL DEFAULT 0,
    description TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id          TEXT PRIMARY KEY,
    employee    TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ranges (
    id        BIGSERIAL PRIMARY KEY,
    tag_id    TEXT NOT NULL,
    anchor_id TEXT NOT NULL REFERENCES anchors(id),
    ts        TIMESTAMPTZ NOT NULL,
    distance  DOUBLE PRECISION NOT NULL,   -- metros
    rssi      DOUBLE PRECISION,
    raw       JSONB
);
CREATE INDEX IF NOT EXISTS idx_ranges_tag_ts ON ranges (tag_id, ts DESC);

CREATE TABLE IF NOT EXISTS positions (
    id       BIGSERIAL PRIMARY KEY,
    tag_id   TEXT NOT NULL,
    ts       TIMESTAMPTZ NOT NULL,
    x        DOUBLE PRECISION NOT NULL,
    y        DOUBLE PRECISION NOT NULL,
    z        DOUBLE PRECISION NOT NULL DEFAULT 0,
    quality  DOUBLE PRECISION,             -- residuo del ajuste (menor = mejor)
    n_anchors SMALLINT
);
CREATE INDEX IF NOT EXISTS idx_positions_tag_ts ON positions (tag_id, ts DESC);

-- Configuración inicial para 5 MaUWB: 4 anchors (A0-A3) + 1 tag (T0).
-- Local medido: aprox. 7.4 x 4.4 m. Eje X y eje Y en metros desde el origen
-- (0,0) elegido en el montaje. Todos los anchors a 0.8 m de altura; el tag
-- circula a 1.0 m (RTLS_TAG_HEIGHT).
INSERT INTO anchors (id, x, y, z, description) VALUES
    ('A0', 6.2,  2.2,  0.8, 'Pasarela USB (COM3)'),
    ('A1', 7.37, 4.4,  0.8, 'Anchor A1'),
    ('A2', 0.0,  4.4,  0.8, 'Anchor A2'),
    ('A3', 0.0,  0.67, 0.8, 'Anchor A3')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tags (id, employee) VALUES ('T0', 'Tag de pruebas')
ON CONFLICT (id) DO NOTHING;
