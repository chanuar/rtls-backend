"""Motor MQTT -> trilateracion -> PostgreSQL -> MQTT.

El formato recomendado agrupa en un ciclo todas las distancias que entrega el
MaUWB. El formato antiguo de una distancia por mensaje sigue aceptado para no
romper clientes existentes.

Ejecutar: python -m rtls.engine
"""
from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import paho.mqtt.client as mqtt
import psycopg

from . import config
from .positioning.kalman import KalmanFilter2D
from .positioning.trilateration import project_to_2d, trilaterate

log = logging.getLogger("rtls.engine")


def _timestamp(value: object | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise ValueError("ts debe ser una fecha ISO 8601")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("ts debe incluir zona horaria")
    return parsed


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} debe ser texto no vacio")
    return value.strip()


def _number(value: object, name: str, *, positive: bool = False) -> float:
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} no es valido")
    return result


def _cycle(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("cycle debe ser un numero o texto")
    return _id(str(value), "cycle")


class Engine:
    def __init__(self) -> None:
        self.db = psycopg.connect(config.DATABASE_URL, autocommit=True)
        self.anchors = self._load_anchors()
        self.buffer: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
        self.filters: dict[str, KalmanFilter2D] = defaultdict(
            lambda: KalmanFilter2D(config.KF_PROCESS_NOISE, config.KF_MEASUREMENT_NOISE)
        )
        self.last_position_ts: dict[str, float] = {}
        self.last_position: dict[str, np.ndarray] = {}
        self.last_cycle: dict[str, str] = {}

        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_message = self._on_message

    def _load_anchors(self) -> dict[str, tuple[float, float, float]]:
        with self.db.cursor() as cur:
            cur.execute("SELECT id, x, y, z FROM anchors")
            anchors = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}
        if not anchors:
            raise RuntimeError("No hay anchors en la BD. Carga sql/schema.sql.")
        log.info("Anchors cargados: %s", list(anchors))
        return anchors

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        log.info("Conectado a MQTT (%s)", reason_code)
        client.subscribe(config.TOPIC_RANGES)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload)
            if "ranges" in payload:
                self._handle_cycle(payload)
            else:
                self._handle_range(payload)
        except Exception:
            log.exception("Mensaje invalido en %s: %r", msg.topic, msg.payload[:200])

    def _handle_cycle(self, payload: dict) -> None:
        tag = _id(payload.get("tag"), "tag")
        cycle = _cycle(payload.get("cycle"))
        ts = _timestamp(payload.get("ts"))
        if self.last_cycle.get(tag) == cycle:
            log.debug("Ciclo duplicado %s/%s ignorado", tag, cycle)
            return

        raw_ranges = payload.get("ranges")
        if not isinstance(raw_ranges, list) or not raw_ranges:
            raise ValueError("ranges debe ser una lista no vacia")

        distances: dict[str, float] = {}
        rows = []
        for item in raw_ranges:
            if not isinstance(item, dict):
                raise ValueError("cada rango debe ser un objeto")
            anchor = _id(item.get("anchor"), "anchor")
            if anchor not in self.anchors:
                raise ValueError(f"anchor desconocido: {anchor}")
            if anchor in distances:
                raise ValueError(f"anchor repetido en el ciclo: {anchor}")
            distance = _number(item.get("distance"), "distance", positive=True)
            rssi = None if item.get("rssi") is None else _number(item["rssi"], "rssi")
            az = self.anchors[anchor][2]
            distances[anchor] = project_to_2d(distance, az, config.TAG_HEIGHT)
            rows.append((tag, anchor, ts, distance, rssi, json.dumps(payload)))

        self._store_ranges(tag, rows)
        self.last_cycle[tag] = cycle
        if len(distances) < config.MIN_ANCHORS:
            log.warning(
                "Ciclo %s/%s guardado sin posicion: %d anchors",
                tag, cycle, len(distances),
            )
            return
        self._calculate_position(tag, ts, distances)

    def _handle_range(self, payload: dict) -> None:
        """Compatibilidad con el formato historico de un rango por mensaje."""
        tag = _id(payload.get("tag"), "tag")
        anchor = _id(payload.get("anchor"), "anchor")
        distance = _number(payload.get("distance"), "distance", positive=True)
        rssi = None if payload.get("rssi") is None else _number(payload["rssi"], "rssi")
        ts = _timestamp(payload.get("ts"))
        if anchor not in self.anchors:
            log.warning("Rango de anchor desconocido %s ignorado", anchor)
            return

        self._store_ranges(tag, [(tag, anchor, ts, distance, rssi, json.dumps(payload))])
        az = self.anchors[anchor][2]
        self.buffer[tag][anchor] = (ts.timestamp(), project_to_2d(distance, az, config.TAG_HEIGHT))
        self._try_position(tag, ts)

    def _store_ranges(self, tag: str, rows: list[tuple]) -> None:
        with self.db.cursor() as cur:
            cur.execute("INSERT INTO tags (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (tag,))
            cur.executemany(
                "INSERT INTO ranges (tag_id, anchor_id, ts, distance, rssi, raw)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                rows,
            )

    def _try_position(self, tag: str, ts: datetime) -> None:
        now = ts.timestamp()
        fresh = {
            anchor: (measured_at, distance)
            for anchor, (measured_at, distance) in self.buffer[tag].items()
            if now - measured_at <= config.RANGE_WINDOW_S
        }
        self.buffer[tag] = fresh
        if len(fresh) >= config.MIN_ANCHORS:
            self._calculate_position(tag, ts, {anchor: value[1] for anchor, value in fresh.items()})

    def _calculate_position(self, tag: str, ts: datetime, distances: dict[str, float]) -> None:
        anchor_ids = list(distances)
        anchors_xy = np.array([self.anchors[anchor][:2] for anchor in anchor_ids])
        measured = np.array([distances[anchor] for anchor in anchor_ids])
        try:
            raw_position, rms = trilaterate(
                anchors_xy, measured, initial_guess=self.last_position.get(tag)
            )
        except Exception:
            log.exception("Trilateracion fallida para %s", tag)
            return

        now = ts.timestamp()
        dt = now - self.last_position_ts.get(tag, now)
        filtered = self.filters[tag].update(raw_position, dt)
        self.last_position_ts[tag] = now
        self.last_position[tag] = filtered

        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO positions (tag_id, ts, x, y, z, quality, n_anchors)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (tag, ts, float(filtered[0]), float(filtered[1]),
                 config.TAG_HEIGHT, rms, len(anchor_ids)),
            )
        self.mqtt.publish(
            f"{config.TOPIC_POSITIONS}/{tag}",
            json.dumps({
                "tag": tag,
                "ts": ts.isoformat(),
                "x": round(float(filtered[0]), 3),
                "y": round(float(filtered[1]), 3),
                "quality": round(rms, 3),
                "n_anchors": len(anchor_ids),
            }),
        )
        log.debug("%s -> (%.2f, %.2f) rms=%.2f n=%d", tag, filtered[0], filtered[1], rms, len(anchor_ids))

    def run(self) -> None:
        self.mqtt.connect(config.MQTT_HOST, config.MQTT_PORT)
        log.info("Motor de posicionamiento arrancado")
        self.mqtt.loop_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    Engine().run()
