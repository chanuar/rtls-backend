import os
import math

MQTT_HOST = os.getenv("RTLS_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("RTLS_MQTT_PORT", "1883"))

TOPIC_RANGES = os.getenv("RTLS_TOPIC_RANGES", "rtls/ranges")
TOPIC_POSITIONS = os.getenv("RTLS_TOPIC_POSITIONS", "rtls/positions")

DATABASE_URL = os.getenv(
    "RTLS_DATABASE_URL",
    "postgresql://rtls:rtls@localhost:5432/rtls",
)

# Ventana temporal (s) para agrupar rangos de un tag antes de trilaterar
RANGE_WINDOW_S = float(os.getenv("RTLS_RANGE_WINDOW_S", "2.0"))
MIN_ANCHORS = int(os.getenv("RTLS_MIN_ANCHORS", "3"))
# Altura media a la que se lleva el tag (m), para corregir distancias 3D→2D
TAG_HEIGHT = float(os.getenv("RTLS_TAG_HEIGHT", "1.2"))
RANGE_HEIGHT_TOLERANCE = float(os.getenv("RTLS_RANGE_HEIGHT_TOLERANCE", "0.1"))
MAX_RMS = float(os.getenv("RTLS_MAX_RMS", "0.5"))
if not math.isfinite(RANGE_HEIGHT_TOLERANCE) or RANGE_HEIGHT_TOLERANCE < 0:
    raise ValueError("RTLS_RANGE_HEIGHT_TOLERANCE debe ser finita y >= 0")
if not math.isfinite(MAX_RMS) or MAX_RMS <= 0:
    raise ValueError("RTLS_MAX_RMS debe ser finito y > 0")

KF_PROCESS_NOISE = float(os.getenv("RTLS_KF_PROCESS_NOISE", "0.5"))   # m/s²
KF_MEASUREMENT_NOISE = float(os.getenv("RTLS_KF_MEAS_NOISE", "0.3"))  # m
