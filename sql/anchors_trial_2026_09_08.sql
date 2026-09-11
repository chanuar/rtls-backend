-- Montaje de prueba medido el 2026-09-08. Coordenadas en metros.
-- Conserva rangos y posiciones historicos, sin recalcularlos.
BEGIN;
INSERT INTO anchors (id, x, y, z, description) VALUES
    ('A0', 6.5, 1.5, 1.00, 'Pasarela USB'),
    ('A1', 8.0, 3.2, 1.66, 'Anchor A1'),
    ('A2', 1.7, 3.2, 0.88, 'Anchor A2'),
    ('A3', 0.0, 0.0, 0.97, 'Anchor A3')
ON CONFLICT (id) DO UPDATE SET
    x = EXCLUDED.x, y = EXCLUDED.y, z = EXCLUDED.z;
COMMIT;
