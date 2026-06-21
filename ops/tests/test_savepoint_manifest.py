#!/usr/bin/env python3

from __future__ import annotations

import json
import pathlib
import re
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
SAVEPOINT = ROOT_DIR / "ops/savepoints/20260621-202754-good-mining-state.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class SavepointManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(SAVEPOINT.read_text(encoding="utf-8"))

    def test_manifest_pins_source_and_runtime_state(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(
            self.manifest["savepoint_id"],
            "20260621-202754-stack-redis-good-mining-state",
        )

        expected_repos = {"stack-redis", "pool", "blockdag-corechain", "redis-dash"}
        self.assertEqual(set(self.manifest["source_commits"]), expected_repos)
        for repo, state in self.manifest["source_commits"].items():
            self.assertTrue(state["branch"], repo)
            self.assertRegex(state["commit"], HEX40, repo)

        expected_images = {
            "stack-node",
            "stack-pool",
            "stack-dashboard",
            "stack-status-sampler",
            "stack-watchdog",
            "stack-sentinel",
        }
        self.assertEqual(set(self.manifest["runtime_images"]), expected_images)
        for image, digest in self.manifest["runtime_images"].items():
            self.assertRegex(digest, SHA256, image)

    def test_non_regression_contract_keeps_mining_safety_gates(self) -> None:
        contract = self.manifest["non_regression_contract"]
        gates = contract["minimum_live_gates"]

        self.assertIs(gates["dashboard_can_accept_shares"], True)
        self.assertIs(gates["dashboard_can_submit_blocks"], True)
        self.assertGreaterEqual(gates["node_p2p_fresh_consensus_peer_count"], 2)
        self.assertEqual(gates["pool_active_connections"], 4)
        self.assertEqual(gates["pool_ready_miners"], 4)
        self.assertEqual(gates["asic_ready_lanes"], 4)

        preserve_text = "\n".join(contract["must_preserve"])
        self.assertIn("coinbase", preserve_text)
        self.assertIn("before miner broadcast", preserve_text)
        self.assertIn("ASIC performance rows", preserve_text)

    def test_live_evidence_represents_good_four_asic_state(self) -> None:
        evidence = self.manifest["live_evidence"]
        dashboard = evidence["dashboard_status"]
        node = evidence["node_template_health"]
        pool = evidence["pool_metrics"]
        asics = evidence["asic_performance"]

        self.assertEqual(dashboard["mode"], "mining")
        self.assertIs(dashboard["can_accept_shares"], True)
        self.assertIs(dashboard["can_submit_blocks"], True)
        self.assertEqual(dashboard["miner_health"], {"managed": 4, "connected": 4, "configured": 4})

        self.assertIs(node["mineable_now"], True)
        self.assertIs(node["submit_ready"], True)
        self.assertIs(node["get_block_template_ready"], True)
        self.assertEqual(node["sync_reason_code"], "ok")
        self.assertIs(node["p2p_mining_fresh"], True)
        self.assertGreaterEqual(node["p2p_fresh_consensus_peer_count"], 2)
        self.assertIs(node["chain_current"], True)

        self.assertEqual(pool["active_connections"], 4)
        self.assertEqual(pool["ready_miners"], 4)
        self.assertGreater(pool["block_submit_outcomes"]["accepted_ok"], 0)

        self.assertEqual(asics["lanes"], 4)
        self.assertEqual(asics["ready"], 4)
        self.assertEqual(asics["accepted_30m"], 566)
        self.assertEqual(
            sum(lane["blocks_30m"] for lane in asics["lanes_detail"]),
            asics["accepted_30m"],
        )

    def test_asic_identity_baseline_is_explicit(self) -> None:
        lanes = self.manifest["live_evidence"]["asic_performance"]["lanes_detail"]
        by_mac = {lane["asic_mac"]: lane for lane in lanes}
        self.assertEqual(
            set(by_mac),
            {
                "28:e2:97:1e:c0:b5",
                "28:e2:97:3e:39:63",
                "28:e2:97:4d:44:3a",
                "2a:71:c7:f5:1f:1e",
            },
        )
        self.assertEqual(by_mac["28:e2:97:1e:c0:b5"]["remote_host"], "192.168.1.101")
        self.assertEqual(by_mac["28:e2:97:3e:39:63"]["remote_host"], "192.168.1.14")
        self.assertEqual(by_mac["28:e2:97:4d:44:3a"]["remote_host"], "192.168.1.105")
        self.assertEqual(by_mac["2a:71:c7:f5:1f:1e"]["remote_host"], "192.168.1.102")
        for lane in by_mac.values():
            self.assertIs(lane["ready"], True)
            self.assertEqual(lane["health"], "ok")
            self.assertGreater(lane["blocks_30m"], 0)

    def test_zero_coinbase_follow_up_does_not_weaken_fail_closed_rule(self) -> None:
        follow_up = self.manifest["known_follow_up"]
        rejects = self.manifest["live_evidence"]["pool_metrics"]["template_coinbase_rejects"]

        self.assertGreater(rejects["ws_push_zero_template_address"], 0)
        self.assertIn("zero-template-address", follow_up["issue"])
        self.assertIn("fix upstream", follow_up["policy"])
        self.assertIn("Do not weaken", follow_up["policy"])
        self.assertIn("zero-coinbase templates", follow_up["policy"])


if __name__ == "__main__":
    unittest.main()
