from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg

from rtls import config

NOISE_STD = 0.10
UPDATE_PERIOD = 1.0


class WalkingTag:
    def __init__(self, tag_id: str, anchors: dict[str, tuple[float, float, float]]):
        self.id = tag_id
        self.anchors = anchors
        self.walk_x = (min(a[0] for a in anchors.values()), max(a[0] for a in anchors.values()))
        self.walk_y = (min(a[1] for a in anchors.values()), max(a[1] for a in anchors.values()))
        self.x = random.uniform(*self.walk_x)
        self.y = random.uniform(*self.walk_y)
        self.target = (random.uniform(*self.walk_x), random.uniform(*self.walk_y))
        self.speed = random.uniform(0.6, 1.2)

    def step(self, dt: float) -> None:
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        if distance < 0.3:
            if random.random() < 0.3:
                self.target = (random.uniform(*self.walk_x), random.uniform(*self.walk_y))
            return
        movement = min(self.speed * dt, distance)
        self.x += dx / distance * movement
        self.y += dy / distance * movement

    def cycle(self, sequence: int) -> dict:
        ranges = []
        for anchor, (ax, ay, az) in self.anchors.items():
            real = math.sqrt((self.x - ax) ** 2 + (self.y - ay) ** 2 + (az - config.TAG_HEIGHT) ** 2)
            ranges.append({
                "anchor": anchor,
                "distance": max(0.001, round(real + random.gauss(0, NOISE_STD), 3)),
                "rssi": round(random.uniform(-85, -70), 1),
            })
        return {
            "tag": self.id,
            "cycle": sequence,
            "ts": datetime.now(timezone.utc).isoformat(),
            "ranges": ranges,
        }


def main() -> None:
    with psycopg.connect(config.DATABASE_URL) as db, db.cursor() as cur:
        cur.execute("SELECT id, x, y, z FROM anchors WHERE id IN ('A0', 'A1', 'A2', 'A3') ORDER BY id")
        anchors = {row[0]: tuple(row[1:]) for row in cur.fetchall()}
    if len(anchors) != 4 or not all(math.isfinite(v) for xyz in anchors.values() for v in xyz):
        raise ValueError("Se necesitan coordenadas finitas de A0-A3 en PostgreSQL")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(config.MQTT_HOST, config.MQTT_PORT)
    client.loop_start()
    tag = WalkingTag("T0", anchors)
    print(f"Simulando T0 con 4 anchors -> mqtt://{config.MQTT_HOST}:{config.MQTT_PORT}/{config.TOPIC_RANGES} (Ctrl+C para parar)")

    last = time.time()
    sequence = 0
    while True:
        now = time.time()
        tag.step(now - last)
        last = now
        client.publish(config.TOPIC_RANGES, json.dumps(tag.cycle(sequence)))
        sequence = (sequence + 1) % 256
        time.sleep(UPDATE_PERIOD)


if __name__ == "__main__":
    main()
