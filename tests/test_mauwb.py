import json
import unittest
from itertools import combinations
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import psycopg

from rtls import config
from rtls.api import _on_mqtt_connect
from rtls.engine import Engine
from rtls.positioning.trilateration import project_to_2d, trilaterate
from tools.mauwb_gateway import parse_at_range
from tools.simulator import WalkingTag


ANCHORS = {"A0": (6.2, 2.2, 0.8), "A1": (7.37, 4.4, 0.8),
           "A2": (0.0, 4.4, 0.8), "A3": (0.0, 0.67, 0.8)}
START = datetime(2026, 8, 17, tzinfo=timezone.utc)


def cycle(position=(4.0, 2.0), sequence=1):
    return {"tag": "T0", "cycle": sequence,
            "ts": (START + timedelta(seconds=sequence)).isoformat(),
            "ranges": [{"anchor": anchor, "distance": float(np.linalg.norm(
                np.array(xyz) - [*position, config.TAG_HEIGHT]))}
                for anchor, xyz in ANCHORS.items()]}


class MaUWBTest(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock(closed=False)
        self.db.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            (anchor, *xyz) for anchor, xyz in ANCHORS.items()]
        with patch("rtls.engine.psycopg.connect", return_value=self.db), patch("rtls.engine.mqtt.Client"):
            self.engine = Engine()

    def test_parser_supports_current_and_rssiless_firmware(self):
        parsed = parse_at_range("AT+RANGE=tid:0,mask:03,seq:182,range:(232,401,0,0),"
                                "rssi:(-79.80,-81.10,0,0),ancid:(0,1,-1,-1)")
        self.assertEqual(parsed["tag"], "T0")
        self.assertEqual(parsed["cycle"], 182)
        self.assertEqual(parsed["ranges"][0], {"anchor": "A0", "distance": 2.32, "rssi": -79.8})
        parsed = parse_at_range("AT+RANGE=tid:0,mask:01,seq:183,range:(250,0),ancid:(3,-1)")
        self.assertEqual(parsed["ranges"], [{"anchor": "A3", "distance": 2.5}])

    def test_known_positions_with_real_solver(self):
        anchors = np.array(list(ANCHORS.values()))
        for point in [(0.0, 0.0), (0.8, 0.7), (3.7, 2.2), (7.4, 4.4), (4, 2)]:
            for indices in [*combinations(range(4), 3), (0, 1, 2, 3)]:
                selected = anchors[list(indices)]
                with self.subTest(point=point, indices=indices):
                    distances = [project_to_2d(np.linalg.norm(a - [*point, config.TAG_HEIGHT]),
                                               a[2], config.TAG_HEIGHT) for a in selected]
                    actual, rms = trilaterate(selected[:, :2], distances)
                    np.testing.assert_allclose(actual, point, atol=1e-5)
                    self.assertLess(rms, 1e-5)

    def test_impossible_projection_and_noise_tolerance(self):
        self.assertAlmostEqual(project_to_2d(5.0, 4.0, 1.0), 4.0)
        self.assertAlmostEqual(project_to_2d(5.0, 1.0, 4.0), 4.0)
        with self.assertRaises(ValueError):
            project_to_2d(0.5, 3, 1.2)
        self.assertLess(project_to_2d(1.75, 3, 1.2, tolerance=0.1), 0.01)
        with self.assertRaises(ValueError):
            project_to_2d(1.75, 3, 1.2, tolerance=0.01)

    def test_invalid_geometry_and_failed_solver(self):
        for anchors in ([[0, 0], [1, 0], [2, 0]], [[0, 0]] * 3):
            with self.assertRaises(ValueError):
                trilaterate(anchors, [1, 2, 3])
        with patch("rtls.positioning.trilateration.least_squares",
                   return_value=SimpleNamespace(success=False)):
            with self.assertRaises(ValueError):
                trilaterate([[0, 0], [1, 0], [0, 1]], [1, 1, 1])

    def test_one_real_position_per_cycle_and_stale_rejection(self):
        self.engine._handle_cycle(cycle())
        self.engine._handle_cycle(cycle())
        self.engine._handle_cycle(cycle(sequence=0))
        self.engine.mqtt.publish.assert_called_once()
        np.testing.assert_allclose(self.engine.last_position["T0"], [4, 2], atol=1e-5)
        payload = cycle(sequence=2)
        payload["ranges"] = payload["ranges"][:2]
        self.engine._handle_cycle(payload)
        self.engine.mqtt.publish.assert_called_once()

    def test_solver_escapes_wrong_basin_from_bad_seed(self):
        """La semilla no debe poder encallar el ajuste en el minimo espejo."""
        anchors = np.array(list(ANCHORS.values()))
        point = (4.0, 2.0)
        distances = [project_to_2d(np.linalg.norm(a - [*point, config.TAG_HEIGHT]),
                                   a[2], config.TAG_HEIGHT) for a in anchors]
        for seed in [(0.0, 0.0), (27.5, 5.1), (4.0, -30.0), (500.0, 500.0)]:
            with self.subTest(seed=seed):
                actual, rms = trilaterate(anchors[:, :2], distances,
                                          initial_guess=np.array(seed))
                np.testing.assert_allclose(actual, point, atol=1e-5)
                self.assertLess(rms, 1e-5)

    def test_ambiguous_outlier_is_rejected_and_raw_ranges_preserved(self):
        self.engine._handle_cycle(cycle())
        before = self.engine.filters["T0"].x.copy()
        payload = cycle(sequence=2)
        horizontal = [3.15534034, 5.68642585, 3.88428194, 5.20985108]
        for item, distance in zip(payload["ranges"], horizontal):
            dz = ANCHORS[item["anchor"]][2] - config.TAG_HEIGHT
            item["distance"] = float(np.hypot(distance, dz))
        self.engine._handle_cycle(payload)
        self.engine.mqtt.publish.assert_called_once()
        np.testing.assert_array_equal(self.engine.filters["T0"].x, before)
        stored = self.db.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
        self.assertEqual(len(stored), 4)

    def test_simulator_uses_supplied_survey_and_configured_height(self):
        tag = WalkingTag("T0", ANCHORS)
        tag.x, tag.y = 4.0, 2.0
        with patch("tools.simulator.random.gauss", return_value=0):
            payload = tag.cycle(1)
        self.engine._handle_cycle(payload)
        np.testing.assert_allclose(self.engine.last_position["T0"], [4, 2], atol=0.002)

    def test_bad_fit_does_not_change_filter(self):
        """Una ronda incompatible no debe alterar el filtro."""
        self.engine._handle_cycle(cycle())
        before = self.engine.filters["T0"].x.copy()
        payload = cycle(sequence=2)
        payload["ranges"][0]["distance"] += 20
        self.engine._handle_cycle(payload)
        np.testing.assert_array_equal(self.engine.filters["T0"].x, before)
        self.engine.mqtt.publish.assert_called_once()

    def test_impossible_range_excluded_but_stored(self):
        payload = cycle()
        payload["ranges"][0]["distance"] = 0.01
        self.engine._handle_cycle(payload)
        published = json.loads(self.engine.mqtt.publish.call_args.args[1])
        self.assertEqual(published["n_anchors"], 3)
        self.assertAlmostEqual(published["x"], 4)
        stored = self.db.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
        self.assertEqual(len(stored), 4)

    def test_stale_legacy_input_and_future_window(self):
        self.engine._handle_cycle(cycle(sequence=2))
        self.engine._handle_range({"tag": "T0", "anchor": "A0", "distance": 3,
                                   "ts": START.isoformat()})
        self.assertFalse(self.engine.buffer["T0"])
        now = START.timestamp()
        self.engine.buffer["T0"] = {"A0": (now + 1, 3), "A1": (now, 3), "A2": (now - 10, 3)}
        self.engine._try_position("T0", START)
        self.assertEqual(set(self.engine.buffer["T0"]), {"A1"})

    def test_failed_position_write_preserves_filter(self):
        self.engine._handle_cycle(cycle())
        before = self.engine.filters["T0"].x.copy()
        self.db.cursor.return_value.__enter__.return_value.execute.side_effect = psycopg.OperationalError("offline")
        with self.assertRaises(psycopg.OperationalError):
            self.engine._calculate_position("T0", START + timedelta(seconds=2),
                                            {a: np.linalg.norm(np.array(xyz[:2]) - [5, 2])
                                             for a, xyz in ANCHORS.items()})
        np.testing.assert_array_equal(self.engine.filters["T0"].x, before)
        self.assertEqual(self.engine.last_position_ts["T0"], (START + timedelta(seconds=1)).timestamp())

    def test_database_recovers_on_next_message(self):
        message = SimpleNamespace(payload=json.dumps(cycle()).encode(), topic=config.TOPIC_RANGES)
        with patch.object(self.engine, "_load_anchors", side_effect=psycopg.OperationalError("offline")):
            self.engine._on_message(None, None, message)
        self.db.close.assert_called_once()
        self.db.closed = True
        with patch("rtls.engine.psycopg.connect", return_value=self.db) as connect:
            self.engine._on_message(None, None, message)
        connect.assert_called_once()
        self.engine.mqtt.publish.assert_called_once()

    def test_calibration_refresh_resets_tracking(self):
        self.engine._handle_cycle(cycle())
        changed = {a: (x + 1, y, z) for a, (x, y, z) in ANCHORS.items()}
        message = SimpleNamespace(payload=json.dumps(cycle(sequence=2)).encode(), topic=config.TOPIC_RANGES)
        with patch.object(self.engine, "_load_anchors", return_value=changed):
            self.engine._on_message(None, None, message)
        np.testing.assert_allclose(self.engine.last_position["T0"], [5, 2], atol=1e-5)

    def test_mqtt_subscription_on_each_connection(self):
        client = Mock()
        for _ in range(2):
            _on_mqtt_connect(client, None, None, SimpleNamespace(is_failure=False), None)
        self.assertEqual(client.subscribe.call_count, 2)
        client.subscribe.assert_called_with(f"{config.TOPIC_POSITIONS}/#")
        _on_mqtt_connect(client, None, None, SimpleNamespace(is_failure=True), None)
        self.assertEqual(client.subscribe.call_count, 2)

    def test_windows_api_loop_factory_is_supported(self):
        import asyncio
        from uvicorn import Config

        factory = Config("rtls.api:app", loop="asyncio:SelectorEventLoop").get_loop_factory()
        self.assertIs(factory, asyncio.SelectorEventLoop)


if __name__ == "__main__":
    unittest.main()
