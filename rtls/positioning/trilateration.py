"""Trilateración 2D por mínimos cuadrados no lineales.

Dadas distancias del tag a N anchors (N >= 3), estima (x, y) minimizando
los residuos  ||p - anchor_i|| - d_i  con Levenberg-Marquardt / TRF (SciPy).

Las distancias UWB son 3D (anchor a 3 m de altura, tag a ~1.2 m); antes de
resolver en 2D se proyectan al plano horizontal con Pitágoras.
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

    if initial_guess is None:
        initial_guess = anchors_xy.mean(axis=0)

    def residuals(p: np.ndarray) -> np.ndarray:
        return np.linalg.norm(anchors_xy - p, axis=1) - distances

    result = least_squares(residuals, initial_guess, method="lm")
    if not result.success or not np.isfinite(result.x).all() or not np.isfinite(result.fun).all():
        raise ValueError("La trilateracion no converge a una posicion finita")
    rms = float(np.sqrt(np.mean(result.fun**2)))
    return result.x, rms
