"""Trilateración 2D por mínimos cuadrados no lineales.

Dadas distancias del tag a N anchors (N >= 3), estima (x, y) minimizando
los residuos  ||p - anchor_i|| - d_i  con Levenberg-Marquardt / TRF (SciPy).

Las distancias UWB son 3D; antes de resolver en 2D se proyectan al plano
horizontal con Pitágoras usando las alturas medidas de anchors y tag.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


def project_to_2d(distance_3d: float, anchor_z: float, tag_z: float, tolerance: float = 0.1) -> float:
    """Convierte la distancia 3D medida en distancia horizontal 2D."""
    dz = anchor_z - tag_z
    if not np.isfinite([distance_3d, anchor_z, tag_z, tolerance]).all() or distance_3d <= 0 or tolerance < 0:
        raise ValueError("Distancia, altura o tolerancia invalida")
    if distance_3d < abs(dz) - tolerance:
        raise ValueError("Distancia menor que la separacion vertical")
    horiz_sq = distance_3d**2 - dz**2
    # Si la medida es menor que la diferencia de altura (ruido), acotar a ~0
    return float(np.sqrt(max(horiz_sq, 1e-6)))


def trilaterate(
    anchors_xy: np.ndarray,   # shape (N, 2)
    distances: np.ndarray,    # shape (N,) distancias horizontales en metros
    initial_guess: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """Devuelve ((x, y), residuo_rms).

    residuo_rms es una medida de calidad: metros de desajuste medio entre
    las distancias medidas y la posición estimada. >0.5 m suele indicar
    NLOS (obstáculos) o una medida mala.
    """
    anchors_xy = np.asarray(anchors_xy, dtype=float)
    distances = np.asarray(distances, dtype=float)

    if anchors_xy.ndim != 2 or anchors_xy.shape[1] != 2 or len(anchors_xy) < 3:
        raise ValueError("Se necesitan al menos 3 anchors 2D")
    if distances.shape != (len(anchors_xy),) or not np.isfinite(distances).all() or np.any(distances < 0):
        raise ValueError("Distancias invalidas")
    if not np.isfinite(anchors_xy).all() or np.linalg.matrix_rank(anchors_xy - anchors_xy.mean(axis=0)) < 2:
        raise ValueError("Geometria de anchors invalida o colineal")

    def residuals(p: np.ndarray) -> np.ndarray:
        return np.linalg.norm(anchors_xy - p, axis=1) - distances

    best_position: np.ndarray | None = None
    best_rms = float("inf")
    for start in _start_points(anchors_xy, initial_guess):
        result = least_squares(residuals, start, method="lm")
        if not result.success:
            continue
        if not np.isfinite(result.x).all() or not np.isfinite(result.fun).all():
            continue
        rms = float(np.sqrt(np.mean(result.fun**2)))
        if rms < best_rms:
            best_position, best_rms = result.x, rms

    if best_position is None:
        raise ValueError("La trilateracion no converge a una posicion finita")
    return best_position, best_rms


def _start_points(anchors_xy: np.ndarray, initial_guess: np.ndarray | None) -> list[np.ndarray]:
    """Puntos de arranque para el solver, sin repetidos.

    Levenberg-Marquardt es un optimizador local; una geometria alargada puede
    presentar minimos locales. Arrancar solo desde el centroide o desde la ultima posicion puede
    dejar el ajuste atrapado en el minimo equivocado, y si esa posicion se
    rechaza por RMS la semilla nunca se actualiza y el tag queda encallado.
    Se prueban varios arranques y se conserva el de menor residuo.
    """
    candidates = []
    if initial_guess is not None:
        candidates.append(np.asarray(initial_guess, dtype=float))
    candidates.append(anchors_xy.mean(axis=0))
    candidates.extend(anchors_xy)
    low = anchors_xy.min(axis=0)
    high = anchors_xy.max(axis=0)
    candidates.extend([
        np.array([low[0], low[1]]), np.array([low[0], high[1]]),
        np.array([high[0], low[1]]), np.array([high[0], high[1]]),
    ])

    unique: list[np.ndarray] = []
    for candidate in candidates:
        if candidate.shape != (2,) or not np.isfinite(candidate).all():
            continue
        if not any(np.allclose(candidate, kept, atol=1e-9, rtol=0) for kept in unique):
            unique.append(candidate)
    return unique
