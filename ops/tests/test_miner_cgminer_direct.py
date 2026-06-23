#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import sys
import unittest
import unittest.mock


OPS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS_DIR))

import pool_ops  # noqa: E402


class MinerCgminerDirectTests(unittest.TestCase):
    def test_cgminer_devs_falls_back_to_direct_4028_when_mcb_http_resets(self) -> None:
        direct_payload = {
            "DEVS": [
                {
                    "Status": "Alive",
                    "MHS av": 234.0,
                    "MHS 20s": 243.432,
                    "Accepted": 381,
                    "Rejected": 144,
                    "Hardware Errors": 29,
                    "hwerr-ration": 0.005222,
                    "Device Elapsed": 793,
                    "fan0": 1440,
                    "fan1": 1500,
                    "tstemp-0": 64.06,
                    "clock": 775.0,
                    "voltage": 0.72,
                }
            ]
        }

        with unittest.mock.patch.object(
            pool_ops, "miner_request", side_effect=pool_ops.MinerAPIError("connection reset by peer")
        ), unittest.mock.patch.object(pool_ops, "cgminer_request", return_value=direct_payload) as direct:
            devs = pool_ops.get_miner_cgminer_devs("192.168.1.106", timeout=1.0)

        self.assertTrue(devs["direct_cgminer_api"])
        self.assertEqual("Alive", devs["minerstatus"])
        self.assertEqual(243.432, devs["hashrate"])
        self.assertEqual(381, devs["accepted"])
        self.assertEqual("1440 rpm / 1500 rpm", devs["fanspeed"])
        direct.assert_called_once_with("192.168.1.106", "devs", timeout=1.0)

    def test_cgminer_devs_direct_empty_payload_is_unusable(self) -> None:
        with unittest.mock.patch.object(pool_ops, "cgminer_request", return_value={"DEVS": []}):
            with self.assertRaises(pool_ops.MinerAPIError):
                pool_ops.get_miner_cgminer_devs_direct("192.168.1.106", timeout=1.0)


if __name__ == "__main__":
    unittest.main()
