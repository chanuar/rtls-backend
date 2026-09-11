import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
from fastapi import HTTPException

from rtls import api


class ApiRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_queries_recover_after_database_outage(self):
        now = datetime.now(timezone.utc)
        calls = [
            (api.get_anchors, (), []),
            (api.get_tags, (), []),
            (api.get_positions, ("T0", now, now), []),
            (api.get_heatmap, (now, now, 0.5), {"cell": 0.5, "bins": []}),
        ]
        for query, args, expected in calls:
            for during_query in (False, True):
                with self.subTest(query=query.__name__, during_query=during_query):
                    db = MagicMock()
                    db.__aenter__.return_value = db
                    cur = db.cursor.return_value.__aenter__.return_value
                    cur.fetchall = AsyncMock(return_value=[])
                    cur.execute = AsyncMock()
                    if during_query:
                        cur.execute.side_effect = [psycopg.OperationalError("offline"), None]
                        connections = [db, db]
                    else:
                        connections = [psycopg.OperationalError("offline"), db]
                    with patch.object(api.psycopg.AsyncConnection, "connect",
                                      new_callable=AsyncMock, side_effect=connections) as connect:
                        with self.assertRaises(HTTPException) as failure:
                            await query(*args)
                        self.assertEqual(failure.exception.status_code, 503)
                        self.assertEqual(await query(*args), expected)
                        self.assertEqual(connect.await_count, 2)
                        self.assertEqual(db.__aexit__.await_count, 2 if during_query else 1)
