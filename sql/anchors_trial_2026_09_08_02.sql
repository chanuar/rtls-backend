-- Segundo montaje de prueba del 2026-09-08. Coordenadas en metros.
-- T0 aproximadamente a 1.0 m (RTLS_TAG_HEIGHT=1.0).
-- Conserva rangos y posiciones historicos, sin recalcularlos.
BEGIN;
INSERT INTO anchors (id, x, y, z, description) VALUES
    ('A0', 12.0, 0.27, 2.0, 'Pasarela USB'),
    ('A1', 1.6, 5.6, 2.0, 'Anchor A1'),
    ('A2', 1.6, 0.8, 1.9, 'Anchor A2'),
    ('A3', 12.4, 4.6, 2.0, 'Anchor A3')
ON CONFLICT (id) DO UPDATE SET
    x = EXCLUDED.x, y = EXCLUDED.y, z = EXCLUDED.z;
COMMIT;
SELECT CURRENT_TIMESTAMP AS applied_at, id, x, y, z FROM anchors ORDER BY id;
