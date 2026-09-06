from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import paho.mqtt.client as mqtt
import psycopg
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import config

log = logging.getLogger("rtls.api")

_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


def _on_mqtt_connect(client, userdata, flags, reason_code, properties) -> None:
    if not reason_code.is_failure:
        client.subscribe(f"{config.TOPIC_POSITIONS}/#")


def _on_mqtt_message(client, userdata, msg) -> None:
    if _loop is None:
        return
    data = msg.payload.decode()
    for ws in list(_clients):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, data), _loop)


async def _safe_send(ws: WebSocket, data: str) -> None:
    try:
        await ws.send_text(data)
    except Exception:
        _clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    m = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    m.on_connect = _on_mqtt_connect
    m.on_message = _on_mqtt_message
    m.connect(config.MQTT_HOST, config.MQTT_PORT)
    m.loop_start()
    app.state.db = await psycopg.AsyncConnection.connect(config.DATABASE_URL, autocommit=True)
    yield
    m.loop_stop()
    await app.state.db.close()


app = FastAPI(title="RTLS UWB API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir en producción al dominio del frontend
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/anchors")
async def get_anchors():
    async with app.state.db.cursor() as cur:
        await cur.execute("SELECT id, x, y, z, description FROM anchors ORDER BY id")
        rows = await cur.fetchall()
    return [{"id": r[0], "x": r[1], "y": r[2], "z": r[3], "description": r[4]} for r in rows]


@app.get("/tags")
async def get_tags():
    async with app.state.db.cursor() as cur:
        await cur.execute("SELECT id, employee, active FROM tags ORDER BY id")
        rows = await cur.fetchall()
    return [{"id": r[0], "employee": r[1], "active": r[2]} for r in rows]


@app.get("/positions/{tag_id}")
async def get_positions(
    tag_id: str,
    start: datetime = Query(..., description="ISO 8601, UTC"),
    end: datetime = Query(..., description="ISO 8601, UTC"),
):
    async with app.state.db.cursor() as cur:
        await cur.execute(
            "SELECT ts, x, y, quality, n_anchors FROM positions"
            " WHERE tag_id = %s AND ts BETWEEN %s AND %s ORDER BY ts",
            (tag_id, start, end),
        )
        rows = await cur.fetchall()
    return [
        {"ts": r[0].isoformat(), "x": r[1], "y": r[2], "quality": r[3], "n_anchors": r[4]}
        for r in rows
    ]


@app.get("/heatmap")
async def get_heatmap(
    start: datetime = Query(...),
    end: datetime = Query(...),
    cell: float = Query(0.5, gt=0.05, le=5, description="Tamaño de celda en metros"),
    tag_id: str | None = None,
):
    """Rejilla de ocupación: cuántas muestras de posición caen en cada celda."""
    filt = " AND tag_id = %s" if tag_id else ""
    params: list = [cell, cell, start, end] + ([tag_id] if tag_id else [])
    async with app.state.db.cursor() as cur:
        await cur.execute(
            f"SELECT floor(x / %s)::int AS cx, floor(y / %s)::int AS cy, count(*)"
            f" FROM positions WHERE ts BETWEEN %s AND %s{filt}"
            f" GROUP BY cx, cy",
            params,
        )
        rows = await cur.fetchall()
    return {"cell": cell, "bins": [{"cx": r[0], "cy": r[1], "count": r[2]} for r in rows]}


@app.websocket("/ws/positions")
async def ws_positions(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive / ignoramos entradas
    except WebSocketDisconnect:
        _clients.discard(ws)
