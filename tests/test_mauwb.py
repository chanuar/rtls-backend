import unittest
import sys
from types import ModuleType
from unittest.mock import Mock, patch

from tools.mauwb_gateway import parse_at_range


class MaUWBTest(unittest.TestCase):
    def test_parser_supports_current_and_rssiless_firmware(self):
        with_rssi = parse_at_range(
            "AT+RANGE=tid:0,mask:03,seq:182,range:(232,401,0,0),"
            "rssi:(-79.80,-81.10,0,0),ancid:(0,1,-1,-1)"
        )
        self.assertEqual(with_rssi["tag"], "T0")
        self.assertEqual(with_rssi["cycle"], 182)
        self.assertEqual(with_rssi["ranges"][0], {"anchor": "A0", "distance": 2.32, "rssi": -79.8})

        without_rssi = parse_at_range(
            "AT+RANGE=tid:0,mask:01,seq:183,range:(250,0),ancid:(3,-1)"
        )
        self.assertEqual(without_rssi["ranges"], [{"anchor": "A3", "distance": 2.5}])

    def test_one_position_per_cycle(self):
        mqtt = ModuleType("paho.mqtt.client")
        mqtt.CallbackAPIVersion = Mock(VERSION2=2)
        mqtt.Client = Mock()
        paho_mqtt = ModuleType("paho.mqtt")
        paho_mqtt.client = mqtt
        paho = ModuleType("paho")
        paho.mqtt = paho_mqtt
        scipy_optimize = ModuleType("scipy.optimize")
        scipy_optimize.least_squares = Mock()
        scipy = ModuleType("scipy")
        scipy.optimize = scipy_optimize
        modules = {
            "paho": paho,
            "paho.mqtt": paho_mqtt,
            "paho.mqtt.client": mqtt,
            "psycopg": ModuleType("psycopg"),
            "scipy": scipy,
            "scipy.optimize": scipy_optimize,
        }
        sys.modules.pop("rtls.engine", None)
        with patch.dict(sys.modules, modules):
            from rtls.engine import Engine
        self.addCleanup(sys.modules.pop, "rtls.engine", None)
        self.addCleanup(sys.modules.pop, "rtls.positioning.trilateration", None)

        engine = Engine.__new__(Engine)
        engine.anchors = {f"A{i}": (float(i), float(i % 2), 3.0) for i in range(4)}
        engine.last_cycle = {}
        engine._store_ranges = Mock()
        engine._calculate_position = Mock()
        payload = {
            "tag": "T0",
            "cycle": 7,
            "ts": "2026-08-17T10:00:00Z",
            "ranges": [{"anchor": f"A{i}", "distance": 3.0 + i} for i in range(4)],
        }

        engine._handle_cycle(payload)
        engine._handle_cycle(payload)
        engine._store_ranges.assert_called_once()
        engine._calculate_position.assert_called_once()

        payload["cycle"] = 8
        payload["ranges"] = payload["ranges"][:2]
        engine._handle_cycle(payload)
        self.assertEqual(engine._store_ranges.call_count, 2)
        engine._calculate_position.assert_called_once()


if __name__ == "__main__":
    unittest.main()
