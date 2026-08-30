"""Simula el montaje MaUWB de 4 anchors y un tag."""
from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = "localhost"
TOPIC = "rtls/ranges"
ANCHORS = {
    "A0": (0.5, 0.5, 3.0),
    "A1": (0.5, 5.1, 3.0),
    "A2": (27.5, 0.5, 3.0),
    "A3": (27.5, 5.1, 3.0),
}
WALK_X = (0.8, 27.2)
WALK_Y = (0.7, 4.9)
TAG_HEIGHT = 1.2
NOISE_STD = 0.10
UPDATE_PERIOD = 1.0


class WalkingTag:
    def __init__(self, tag_id: str):
        self.id = tag_id
        self.x = random.uniform(*WALK_X)
        self.y = random.uniform(*WALK_Y)
        self.target = (random.uniform(*WALK_X), random.uniform(*WALK_Y))
        self.speed = random.uniform(0.6, 1.2)

    def step(self, dt: float) -> None:
        tx, ty = self.target
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        if distance < 0.3:
            if random.random() < 0.3:
                self.target = (random.uniform(*WALK_X), random.uniform(*WALK_Y))
            return
        movement = min(self.speed * dt, distance)
        self.x += dx / distance * movement
        self.y += dy / distance * movement

    def cycle(self, sequence: int) -> dict:
        ranges = []
        for anchor, (ax, ay, az) in ANCHORS.items():
            real = math.sqrt((self.x - ax) ** 2 + (self.y - ay) ** 2 + (az - TAG_HEIGHT) ** 2)
            ranges.append({
                "anchor": anchor,
                "distance": round(real + random.gauss(0, NOISE_STD), 3),
                "rssi": round(random.uniform(-85, -70), 1),
            })
        return {
            "tag": self.id,
            "cycle": sequence,
            "ts": datetime.now(timezone.utc).isoformat(),
            "ranges": ranges,
        }


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, 1883)
    client.loop_start()
    tag = WalkingTag("T0")
    print(f"Simulando T0 con 4 anchors -> mqtt://{MQTT_HOST}/{TOPIC} (Ctrl+C para parar)")

    last = time.time()
    sequence = 0
    while True:
        now = time.time()
        tag.step(now - last)
        last = now
        client.publish(TOPIC, json.dumps(tag.cycle(sequence)))
        sequence = (sequence + 1) % 256
        time.sleep(UPDATE_PERIOD)


if __name__ == "__main__":
    main()
