#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

OPS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS_DIR))

import stack_status_source  # noqa: E402


class StackStatusSourceTests(unittest.TestCase):
    def test_compact_http_status_falls_back_to_in_process_repair_status(self) -> None:
        compact_dashboard_payload = {
            "status": "degraded",
            "mode": "node_syncing",
            "sync_progress": {"status": "p2p_down"},
        }
        in_process_payload = {
            "failures": [],
            "warnings": ["native P2P is down"],
            "overall": "degraded",
        }

        with mock.patch.object(stack_status_source, "_fixture_payload", return_value=None), mock.patch.object(
            stack_status_source, "_env_urls", return_value=["http://dashboard:8088/api/status"]
        ), mock.patch.object(
            stack_status_source, "fetch_http_status", return_value=compact_dashboard_payload
        ), mock.patch.object(
            stack_status_source, "collect_status_cached", return_value=in_process_payload
        ):
            status = stack_status_source.collect_stack_status()

        self.assertEqual("in-process", status["stack_status_source"]["source"])
        self.assertEqual("degraded", status["overall"])
        self.assertIn("missing repair schema key", status["stack_status_source"]["errors"][0])

    def test_repair_complete_http_status_is_used_directly(self) -> None:
        http_payload = {
            "failures": [],
            "warnings": [],
            "overall": "ok",
        }

        with mock.patch.object(stack_status_source, "_fixture_payload", return_value=None), mock.patch.object(
            stack_status_source, "_env_urls", return_value=["http://dashboard:8088/api/status"]
        ), mock.patch.object(
            stack_status_source, "fetch_http_status", return_value=http_payload
        ), mock.patch.object(
            stack_status_source,
            "collect_status_cached",
            side_effect=AssertionError("complete HTTP status should not fall back"),
        ):
            status = stack_status_source.collect_stack_status()

        self.assertEqual("status-http", status["stack_status_source"]["source"])
        self.assertEqual("ok", status["overall"])


if __name__ == "__main__":
    unittest.main()
