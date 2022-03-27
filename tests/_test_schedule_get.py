#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Test the Schedule functions.
"""

# import asyncio
import json
import unittest

from ramses_rf import Gateway
#

from common import GWY_CONFIG, TEST_DIR  # noqa: F401


class TestSchedule(unittest.IsolatedAsyncioTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.maxDiff = None
        self.gwy = None

    async def test_schedule_get(self):
        self.gwy = Gateway(
            None, packet_dict={}, config=GWY_CONFIG, loop=self._asyncioTestLoop
        )
        with open(f"{TEST_DIR}/logs/system_cache.json") as f:
            system_cache = json.load(f)

        await self.gwy._set_state(**system_cache["data"]["client_state"])

        # self.assertEqual(self.gwy.schema, schema)


if __name__ == "__main__":
    unittest.main()