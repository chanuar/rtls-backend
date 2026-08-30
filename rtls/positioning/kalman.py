"""Filtro de Kalman 2D con modelo de velocidad constante.

Estado: [x, y, vx, vy]. Medida: posición (x, y) de la trilateración.
Elimina saltos y suaviza la trayectoria. Suficiente para la Fase 1;
si más adelante se fusionan medidas de distancia directamente, migrar a EKF.
"""
from __future__ import annotations

import numpy as np


class KalmanFilter2D:
    def __init__(self, process_noise: float = 0.5, measurement_noise: float = 0.3):
        self.q = process_noise       # aceleración esperada (m/s²)
        self.r = measurement_noise   # ruido de medida (m)
        self.x: np.ndarray | None = None  # estado [x, y, vx, vy]
        self.P: np.ndarray | None = None  # covarianza
        self._H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)

    def update(self, measurement: np.ndarray, dt: float) -> np.ndarray:
        """Incorpora una medida (x, y) tomada dt segundos después de la anterior.

        Devuelve la posición filtrada (x, y).
        """
        z = np.asarray(measurement, dtype=float)

        if self.x is None:
            self.x = np.array([z[0], z[1], 0.0, 0.0])
            self.P = np.diag([self.r**2, self.r**2, 1.0, 1.0])
            return self.x[:2].copy()

        dt = max(dt, 1e-3)

        # Predicción
        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=float)
        # Ruido de proceso (modelo de aceleración blanca)
        q = self.q**2
        G = np.array([[0.5 * dt**2, 0], [0, 0.5 * dt**2], [dt, 0], [0, dt]])
        Q = G @ G.T * q

        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

        # Corrección
        R = np.eye(2) * self.r**2
        y = z - self._H @ self.x
        S = self._H @ self.P @ self._H.T + R
        K = self.P @ self._H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ self._H) @ self.P

        return self.x[:2].copy()

    def reset(self) -> None:
        self.x = None
        self.P = None
