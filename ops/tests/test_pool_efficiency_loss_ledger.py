#!/usr/bin/env python3

from collections import Counter
import pathlib
import sys
import unittest

OPS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS_DIR))

import pool_ops  # noqa: E402


class PoolEfficiencyLossLedgerTests(unittest.TestCase):
    def test_loss_ledger_flags_block_share_and_template_waste(self) -> None:
        ledger = pool_ops.build_pool_efficiency_loss_ledger(
            block_submit_outcomes=Counter(
                {
                    "accepted:ok": 100,
                    "rejected:tip-overdue": 40,
                    "rejected-local:duplicate-block": 10,
                }
            ),
            shares_accepted_total=50,
            shares_rejected_by_reason=Counter({"invalidated_job": 70, "non_current_job": 20}),
            block_totals=Counter({"found": 150, "submitted": 150, "mature": 100}),
            blocks_rejected_by_node=Counter({"tip-overdue": 40}),
            share_processing={"count": 10, "sum_seconds": 3},
            template_conversion_stall={"active_miners": 5, "failure_ratio": 42.0},
        )

        self.assertEqual(ledger["severity"], "warning")
        self.assertEqual(ledger["block_outcomes"]["accepted_ratio_percent"], 66.67)
        self.assertEqual(ledger["share_outcomes"]["accepted_ratio_percent"], 35.71)
        self.assertTrue(any("template conversion loss" in item for item in ledger["warnings"]))
        self.assertEqual(ledger["top_loss_reasons"][0]["reason"], "invalidated_job")

    def test_loss_ledger_escalates_critical_template_conversion_loss(self) -> None:
        ledger = pool_ops.build_pool_efficiency_loss_ledger(
            block_submit_outcomes=Counter({"accepted:ok": 20, "rejected:tip-overdue": 10}),
            shares_accepted_total=100,
            shares_rejected_by_reason=Counter(),
            block_totals=Counter(),
            blocks_rejected_by_node=Counter(),
            template_conversion_stall={"active_miners": 5, "failure_ratio": 55.0},
        )

        self.assertEqual(ledger["severity"], "critical")

    def test_readiness_contract_distinguishes_contradiction_from_hard_unready(self) -> None:
        source_health = {"node_mineable": False, "node_submit_ready": False, "node_p2p_mining_fresh": True}
        job_health = {"ok": False}

        contradiction = pool_ops.selected_backend_readiness_contract("node", source_health, job_health, True, True)
        paid_but_not_safe = pool_ops.selected_backend_readiness_contract("node", source_health, job_health, True, False)
        hard_unready = pool_ops.selected_backend_readiness_contract("node", source_health, job_health, False, False)

        self.assertTrue(contradiction["contradiction"])
        self.assertFalse(contradiction["hard_unready"])
        self.assertTrue(contradiction["readiness_override_safe"])
        self.assertTrue(paid_but_not_safe["contradiction"])
        self.assertTrue(paid_but_not_safe["hard_unready"])
        self.assertFalse(paid_but_not_safe["readiness_override_safe"])
        self.assertFalse(hard_unready["contradiction"])
        self.assertTrue(hard_unready["hard_unready"])

    def test_selected_backend_unready_reasons_include_peer_freshness(self) -> None:
        reasons = pool_ops.selected_backend_unready_reasons(
            {
                "node_mineable": False,
                "node_submit_ready": False,
                "node_p2p_mining_fresh": False,
                "node_last_template_build_error_blocking": True,
            }
        )

        self.assertEqual(
            reasons,
            [
                "mineable=false",
                "submit_ready=false",
                "p2p_mining_fresh=false",
                "template_build_error_blocking=true",
            ],
        )

    def test_native_p2p_current_safety_survives_template_readiness_flicker(self) -> None:
        self.assertTrue(
            pool_ops.selected_backend_native_p2p_current_safe(
                {
                    "healthy": True,
                    "node_mineable": False,
                    "node_submit_ready": False,
                    "node_p2p_mining_fresh": True,
                    "node_p2p_fresh_consensus_peer_count": 2,
                    "node_p2p_best_peer_lead_blocks": pool_ops.CATCHUP_NATIVE_P2P_MAX_PEER_LEAD_BLOCKS,
                }
            )
        )

    def test_native_p2p_current_safety_rejects_peer_loss_and_peer_lead(self) -> None:
        peer_loss = {
            "healthy": True,
            "node_p2p_mining_fresh": True,
            "node_p2p_fresh_consensus_peer_count": 1,
            "node_p2p_best_peer_lead_blocks": 0,
        }
        peer_lead = {
            "healthy": True,
            "node_p2p_mining_fresh": True,
            "node_p2p_fresh_consensus_peer_count": 3,
            "node_p2p_best_peer_lead_blocks": pool_ops.CATCHUP_NATIVE_P2P_MAX_PEER_LEAD_BLOCKS + 1,
        }
        stale = {
            "healthy": True,
            "node_p2p_mining_fresh": False,
            "node_p2p_fresh_consensus_peer_count": 3,
            "node_p2p_best_peer_lead_blocks": 0,
        }

        self.assertFalse(pool_ops.selected_backend_native_p2p_current_safe(peer_loss))
        self.assertFalse(pool_ops.selected_backend_native_p2p_current_safe(peer_lead))
        self.assertFalse(pool_ops.selected_backend_native_p2p_current_safe(stale))

    def test_selected_backend_safety_fails_closed_on_unknown_peer_floor_or_lead(self) -> None:
        base = {
            "healthy": True,
            "node_mineable": True,
            "node_submit_ready": True,
            "node_p2p_mining_fresh": True,
            "node_p2p_fresh_consensus_peer_count": 3,
            "node_p2p_best_peer_lead_blocks": 0,
        }

        self.assertTrue(pool_ops.selected_backend_mining_safe(base))
        self.assertTrue(pool_ops.selected_backend_native_p2p_current_safe(base))

        missing_peers = dict(base)
        missing_peers.pop("node_p2p_fresh_consensus_peer_count")
        self.assertFalse(pool_ops.selected_backend_mining_safe(missing_peers))
        self.assertFalse(pool_ops.selected_backend_native_p2p_current_safe(missing_peers))

        missing_lead = dict(base)
        missing_lead.pop("node_p2p_best_peer_lead_blocks")
        self.assertFalse(pool_ops.selected_backend_mining_safe(missing_lead))
        self.assertFalse(pool_ops.selected_backend_native_p2p_current_safe(missing_lead))

        for lead in (10, 11, 12):
            safe = dict(base, node_p2p_best_peer_lead_blocks=lead)
            self.assertTrue(pool_ops.selected_backend_mining_safe(safe), f"lead={lead}")
            self.assertTrue(pool_ops.selected_backend_native_p2p_current_safe(safe), f"lead={lead}")

        unsafe = dict(base, node_p2p_best_peer_lead_blocks=13)
        self.assertFalse(pool_ops.selected_backend_mining_safe(unsafe))
        self.assertFalse(pool_ops.selected_backend_native_p2p_current_safe(unsafe))

    def test_selected_backend_source_degradation_is_advisory_with_recent_paid_work(self) -> None:
        advisory = pool_ops.selected_backend_source_degradation(True, True)
        hard = pool_ops.selected_backend_source_degradation(True, False)

        self.assertTrue(advisory["degraded"])
        self.assertTrue(advisory["advisory"])
        self.assertFalse(advisory["hard"])
        self.assertTrue(hard["hard"])
        self.assertFalse(hard["advisory"])

    def test_catchup_policy_pauses_pool_above_threshold(self) -> None:
        policy = pool_ops.build_catchup_policy(
            {"status": "syncing", "remaining_blocks": 450},
            {"node": {"peer_ahead_blocks": 20}},
            {"pool": {"running": False}},
            {},
        )

        self.assertTrue(policy["active"])
        self.assertTrue(policy["pool_pause_active"])
        self.assertEqual(policy["threshold_blocks"], 300)
        self.assertIn("mining work is intentionally paused", policy["summary"])
        self.assertIn("Leave miners configured", policy["user_message"])
        self.assertEqual(policy["trigger"], "lag_threshold")

    def test_catchup_policy_ignores_remaining_blocks_when_paid_work_recent(self) -> None:
        policy = pool_ops.build_catchup_policy(
            {
                "status": "syncing",
                "remaining_blocks": 14_982,
                "nodes": {"node": {"remaining_blocks": 14_982, "peer_ahead_blocks": 24}},
            },
            {"node": {"remaining_blocks": 14_982, "peer_ahead_blocks": 24}},
            {"pool": {"running": True}},
            {},
            mining_ready=True,
            ignore_remaining_blocks=True,
        )

        self.assertFalse(policy["active"])
        self.assertTrue(policy["mining_ready"])
        self.assertTrue(policy["remaining_blocks_advisory"])
        self.assertEqual(policy["lag_blocks"], 24)

    def test_catchup_policy_treats_evm_lag_as_advisory_when_native_p2p_is_safe(self) -> None:
        source_health = {
            "node_mineable": False,
            "node_submit_ready": False,
            "node_p2p_mining_fresh": True,
            "node_p2p_fresh_consensus_peer_count": 7,
            "node_p2p_best_peer_lead_blocks": 0,
        }
        policy = pool_ops.build_catchup_policy(
            {
                "status": "syncing",
                "remaining_blocks": 14_982,
                "nodes": {"node": {"remaining_blocks": 14_982}},
            },
            {"node": {"remaining_blocks": 14_982}},
            {"pool": {"running": True}},
            source_health,
            mining_ready=pool_ops.selected_backend_native_p2p_current_safe(source_health),
            ignore_remaining_blocks=pool_ops.selected_backend_native_p2p_current_safe(source_health),
        )

        self.assertFalse(policy["active"])
        self.assertEqual(policy["lag_blocks"], 0)
        self.assertTrue(policy["mining_ready"])
        self.assertTrue(policy["remaining_blocks_advisory"])

    def test_catchup_policy_uses_io_pressure_as_primary_trigger(self) -> None:
        policy = pool_ops.build_catchup_policy(
            {"status": "syncing", "remaining_blocks": 80},
            {"node": {"peer_ahead_blocks": 80}},
            {"pool": {"running": True}},
            {"node_mineable": False, "node_submit_ready": False},
            {"iowait_percent": 18.0, "io_some_avg10": 22.0, "io_full_avg10": 23.0},
            mining_ready=False,
        )

        self.assertTrue(policy["active"])
        self.assertEqual(policy["trigger"], "io_pressure")
        self.assertTrue(policy["io_pressure_active"])
        self.assertFalse(policy["lag_threshold_active"])
        self.assertEqual(policy["lag_blocks"], 80)
        self.assertIn("I/O-bound", policy["summary"])
        self.assertIn("I/O pressure drops", policy["next_step"])
        self.assertTrue(any("io_full_avg10" in reason for reason in policy["io_pressure_reasons"]))

    def test_catchup_policy_uses_backend_peer_lead_when_sync_claims_synced(self) -> None:
        policy = pool_ops.build_catchup_policy(
            {"status": "synced", "remaining_blocks": 0},
            {"node": {}},
            {"pool": {"running": True}},
            {
                "node_mineable": False,
                "node_submit_ready": False,
                "node_p2p_mining_fresh": True,
                "node_p2p_best_peer_lead_blocks": 80,
            },
            {"io_full_avg10": 23.0},
            mining_ready=False,
        )

        self.assertTrue(policy["active"])
        self.assertEqual(policy["trigger"], "io_pressure")
        self.assertEqual(policy["lag_blocks"], 80)

    def test_catchup_policy_pauses_backend_unready_under_io_pressure_without_lag(self) -> None:
        policy = pool_ops.build_catchup_policy(
            {"status": "synced", "remaining_blocks": 0},
            {"node": {}},
            {"pool": {"running": True}},
            {"node_mineable": False, "node_submit_ready": False, "node_p2p_mining_fresh": True},
            {"iowait_percent": 21.0, "io_full_avg10": 22.0},
            mining_ready=False,
        )

        self.assertTrue(policy["active"])
        self.assertEqual(policy["trigger"], "io_pressure")
        self.assertEqual(policy["lag_blocks"], 0)
        self.assertTrue(policy["backend_unready_under_pressure"])
        self.assertIn("backend is not ready", policy["summary"])
        self.assertIn("stale or invalid work", policy["user_message"])


class PoolPrometheusMetricsParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_fetch = pool_ops.fetch_text_url
        self.old_pool_containers = pool_ops.POOL_CONTAINERS
        pool_ops.POOL_CONTAINERS = ["asic-pool"]
        self.addCleanup(self.restore_globals)

    def restore_globals(self) -> None:
        pool_ops.fetch_text_url = self.old_fetch
        pool_ops.POOL_CONTAINERS = self.old_pool_containers

    def test_pool_metrics_parse_loss_ledger_and_source_health_contract_inputs(self) -> None:
        metrics = """
pool_active_connections 5
pool_rpc_backend_selected{backend="node",pool_id="0"} 1
pool_rpc_backend_healthy{backend="node",pool_id="0"} 1
pool_rpc_backend_node_health_mineable{backend="node",pool_id="0"} 0
pool_rpc_backend_node_health_submit_ready{backend="node",pool_id="0"} 0
pool_job_health_ok{pool_id="0"} 0
pool_job_health_ready_miners{pool_id="0"} 5
pool_template_conversion_stall_active_miners{pool_id="0"} 5
pool_template_conversion_stall_failure_ratio{pool_id="0"} 55
pool_template_conversion_stall_window_candidates{kind="accepted",pool_id="0"} 2
pool_template_conversion_stall_window_candidates{kind="failed",pool_id="0"} 3
pool_block_submit_outcomes_total{outcome="accepted",pool_id="0",reason="ok"} 10
pool_block_submit_outcomes_total{outcome="rejected",pool_id="0",reason="tip-overdue"} 8
pool_block_submit_backend_outcomes_total{backend="node",outcome="rejected",pool_id="0",reason="tip-overdue"} 8
pool_blocks_found_total{pool_id="0"} 18
pool_blocks_submitted_total{pool_id="0"} 18
pool_blocks_rejected_by_node_total{pool_id="0",reason="tip-overdue"} 8
pool_share_processing_duration_seconds_sum{pool_id="0"} 1.2
pool_share_processing_duration_seconds_count{pool_id="0"} 4
pool_shares_accepted_total{pool_id="0"} 5
pool_shares_rejected_total{pool_id="0",reason="invalidated_job"} 15
"""
        pool_ops.fetch_text_url = lambda *_args, **_kwargs: metrics

        payload = pool_ops.collect_pool_prometheus_metrics(
            {"asic-pool": {"running": True, "network_ips": ["10.0.0.2"]}}
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["active_connections"], 5)
        self.assertEqual(payload["selected_backend"], "node")
        self.assertFalse(payload["selected_backend_source_health"]["node_mineable"])
        self.assertEqual(payload["loss_ledger"]["severity"], "critical")
        self.assertEqual(payload["loss_ledger"]["share_outcomes"]["accepted_ratio_percent"], 25.0)

    def test_pool_metrics_accept_node_label_for_backend_health(self) -> None:
        metrics = """
pool_active_connections 3
pool_rpc_backend_selected{node="node",pool_id="0"} 1
pool_rpc_backend_healthy{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_mineable{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_submit_ready{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_mining_fresh{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_fresh_consensus_peer_count{node="node",pool_id="0"} 3
pool_rpc_backend_node_health_p2p_best_peer_lead_blocks{node="node",pool_id="0"} 0
pool_job_health_ok{pool_id="0"} 1
pool_job_health_ready_miners{pool_id="0"} 3
pool_block_submit_outcomes_total{outcome="accepted",pool_id="0",reason="ok"} 4
"""
        pool_ops.fetch_text_url = lambda *_args, **_kwargs: metrics

        payload = pool_ops.collect_pool_prometheus_metrics(
            {"asic-pool": {"running": True, "network_ips": ["10.0.0.2"]}}
        )

        self.assertEqual(payload["selected_backend"], "node")
        self.assertTrue(payload["selected_backend_source_health"]["healthy"])
        self.assertTrue(payload["selected_backend_source_health"]["node_mineable"])
        self.assertTrue(pool_ops.selected_backend_mining_safe(payload["selected_backend_source_health"]))


if __name__ == "__main__":
    unittest.main()
