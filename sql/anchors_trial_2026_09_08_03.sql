-- Correccion del segundo montaje: intercambiar coordenadas A1/A2, incluida Z.
-- Coordenadas en metros. Conserva los datos historicos sin recalcularlos.
BEGIN;
UPDATE anchors SET x = 1.6, y = 0.8, z = 1.9 WHERE id = 'A1';
UPDATE anchors SET x = 1.6, y = 5.6, z = 2.0 WHERE id = 'A2';
COMMIT;
SELECT CURRENT_TIMESTAMP AS applied_at, id, x, y, z FROM anchors ORDER BY id;
