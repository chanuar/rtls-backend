-- Esquema RTLS UWB
-- ranges es la fuente de verdad (datos crudos, nunca se borran por lógica de negocio)
-- positions es derivado y recalculable

CREATE TABLE IF NOT EXISTS anchors (
    id          TEXT PRIMARY KEY,          -- p.ej. 'A0'
    x           DOUBLE PRECISION NOT NULL, -- metros, medido con cinta métrica
    y           DOUBLE PRECISION NOT NULL,
    z           DOUBLE PRECISION NOT NULL DEFAULT 0,
    description TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id          TEXT PRIMARY KEY,          -- p.ej. 'T0'
    employee    TEXT,                      -- nombre o id interno del empleado
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ranges (
    id        BIGSERIAL PRIMARY KEY,
    tag_id    TEXT NOT NULL,
    anchor_id TEXT NOT NULL REFERENCES anchors(id),
    ts        TIMESTAMPTZ NOT NULL,
    distance  DOUBLE PRECISION NOT NULL,   -- metros
    rssi      DOUBLE PRECISION,            -- opcional, diagnóstico
    raw       JSONB                        -- payload original completo
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
    n_anchors SMALLINT                     -- nº de anchors usados en el cálculo
);
CREATE INDEX IF NOT EXISTS idx_positions_tag_ts ON positions (tag_id, ts DESC);

-- Configuración inicial para 5 MaUWB: 4 anchors (A0-A3) + 1 tag (T0).
-- Local real aproximado: 28 x 5.6 m, planta alargada.
-- Eje X = profundidad desde la fachada/entrada; eje Y = anchura del local.
-- Son valores de arranque: medir cada posición y sustituirlos antes de calibrar.
INSERT INTO anchors (id, x, y, z, description) VALUES
    ('A0', 0.5,  0.5, 3.0, 'Fachada, lado izquierdo; pasarela USB'),
    ('A1', 0.5,  5.1, 3.0, 'Fachada, lado derecho'),
    ('A2', 27.5, 0.5, 3.0, 'Fondo, lado izquierdo'),
    ('A3', 27.5, 5.1, 3.0, 'Fondo, lado derecho')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tags (id, employee) VALUES ('T0', 'Tag de pruebas')
ON CONFLICT (id) DO NOTHING;
