-- Aplicar solo si estas son las coordenadas medidas del montaje actual.
-- No borra ni recalcula rangos o posiciones historicas.
BEGIN;
INSERT INTO anchors (id, x, y, z, description) VALUES
    ('A0', 6.2, 2.2, 0.8, 'Pasarela USB'),
    ('A1', 7.37, 4.4, 0.8, 'Anchor A1'),
    ('A2', 0.0, 4.4, 0.8, 'Anchor A2'),
    ('A3', 0.0, 0.67, 0.8, 'Anchor A3')
ON CONFLICT (id) DO UPDATE SET
    x = EXCLUDED.x, y = EXCLUDED.y, z = EXCLUDED.z;
COMMIT;
