"""Pasarela serie MaUWB AT -> MQTT.

Conecta por USB solo el anchor A0, que recibe la ronda completa del sistema.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone


def _field(line: str, name: str) -> str:
    match = re.search(rf"(?:^|,)\s*{re.escape(name)}:([^,]+)", line)
    if not match:
        raise ValueError(f"falta {name}")
    return match.group(1).strip()


def _array(line: str, name: str) -> list[str]:
    match = re.search(rf"(?:^|,)\s*{re.escape(name)}:\(([^)]*)\)", line)
    if not match:
        raise ValueError(f"falta {name}")
    return [value.strip() for value in match.group(1).split(",")]


def parse_at_range(line: str, distance_scale: float = 0.01) -> dict:
    """Convierte una linea AT+RANGE de Makerfabs al ciclo MQTT del backend."""
    line = line.strip()
    if not line.startswith("AT+RANGE="):
        raise ValueError("no es una linea AT+RANGE")
    body = line.removeprefix("AT+RANGE=")
    tag = int(_field(body, "tid"))
    sequence = int(_field(body, "seq"))
    raw_ranges = _array(body, "range")
    anchor_ids = _array(body, "ancid")
    if len(raw_ranges) != len(anchor_ids):
        raise ValueError("range y ancid tienen distinta longitud")

    try:
        raw_rssi = _array(body, "rssi")
    except ValueError:
        raw_rssi = []

    ranges = []
    for index, (raw_distance, raw_anchor) in enumerate(zip(raw_ranges, anchor_ids)):
        anchor = int(raw_anchor)
        distance = float(raw_distance) * distance_scale
        if anchor < 0 or distance <= 0:
            continue
        item = {"anchor": f"A{anchor}", "distance": round(distance, 4)}
        if index < len(raw_rssi):
            rssi = float(raw_rssi[index])
            if rssi != 0:
                item["rssi"] = rssi
        ranges.append(item)

    if not ranges:
        raise ValueError("la linea no contiene rangos validos")
    return {
        "tag": f"T{tag}",
        "cycle": sequence,
        "ts": datetime.now(timezone.utc).isoformat(),
        "ranges": ranges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica las medidas MaUWB serie en MQTT")
    parser.add_argument("--port", default=os.getenv("MAUWB_SERIAL_PORT"), required=not os.getenv("MAUWB_SERIAL_PORT"))
    parser.add_argument("--baud", type=int, default=int(os.getenv("MAUWB_BAUD", "115200")))
    parser.add_argument("--mqtt-host", default=os.getenv("RTLS_MQTT_HOST", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("RTLS_MQTT_PORT", "1883")))
    parser.add_argument("--topic", default=os.getenv("RTLS_TOPIC_RANGES", "rtls/ranges"))
    parser.add_argument("--distance-scale", type=float, default=float(os.getenv("MAUWB_DISTANCE_SCALE", "0.01")))
    args = parser.parse_args()

    import paho.mqtt.client as mqtt
    import serial

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.mqtt_host, args.mqtt_port)
    client.loop_start()
    print(f"Leyendo {args.port} a {args.baud} baud -> mqtt://{args.mqtt_host}:{args.mqtt_port}/{args.topic}")
    with serial.Serial(args.port, args.baud, timeout=1) as source:
        while True:
            line = source.readline().decode("utf-8", errors="replace").strip()
            if not line.startswith("AT+RANGE="):
                continue
            try:
                payload = parse_at_range(line, args.distance_scale)
            except ValueError as error:
                print(f"Medida descartada: {error}: {line[:160]}")
                continue
            client.publish(args.topic, json.dumps(payload))


if __name__ == "__main__":
    main()
