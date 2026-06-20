#!/usr/bin/env python3

import pathlib
import sys
import unittest

OPS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS_DIR))

import optimization_measurement as measurement  # noqa: E402


class OptimizationMeasurementTests(unittest.TestCase):
    def test_flatten_status_sample_extracts_resource_and_sync_fields(self) -> None:
        payload = {
            "overall": "syncing",
            "mode": "sync_only_no_miners",
            "can_mine": False,
            "sync_progress": {
                "status": "syncing",
                "current_block": 10,
                "highest_block": 15,
                "remaining_blocks": 5,
                "nodes": {
                    "primary": {"chain_rpc_latency_ms": 12.5},
                    "secondary": {"chain_rpc_latency_ms": 8.0},
                },
            },
            "host_pressure": {"iowait_percent": 3.0, "io_some_avg10": 1.0, "cpu_some_avg10": 2.0},
            "miner_health": {"connected_count": 0, "managed_count": 0},
            "adaptive_concurrency": {
                "pressure_level": "low",
                "workers": {"global_rpc": 6},
                "host_profile": {"profile": "pi5", "os": "linux", "arch": "arm64"},
            },
        }

        sample = measurement.flatten_status_sample(payload, "fixture", 4.2, 3.1)

        self.assertEqual(sample["sync_status"], "syncing")
        self.assertEqual(sample["current_block"], 10)
        self.assertEqual(sample["remaining_blocks"], 5)
        self.assertEqual(sample["chain_rpc_latency_ms_max"], 12.5)
        self.assertEqual(sample["adaptive_workers"]["global_rpc"], 6)
        self.assertEqual(sample["dashboard_latency_ms"], 3.1)

    def test_pool_metrics_parser_extracts_mining_quality_fields(self) -> None:
        metrics = measurement.parse_prometheus_metrics(
            """
pool_active_connections{pool_id="0"} 2
pool_job_health_ready_miners{pool_id="0"} 2
pool_block_submit_outcomes_total{outcome="accepted",pool_id="0",reason="ok"} 38
pool_block_submit_outcomes_total{outcome="rejected",pool_id="0",reason="tip-overdue"} 1
pool_block_submit_outcomes_total{outcome="rejected-local",pool_id="0",reason="stale-parent"} 2
pool_blocks_found_total{pool_id="0"} 41
pool_shares_accepted_total{pool_id="0"} 156
pool_shares_rejected_total{pool_id="0",reason="invalidated_job"} 38
pool_rpc_backend_node_health_mineable{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_submit_ready{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_mining_fresh{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_fresh_consensus_peer_count{node="node",pool_id="0"} 4
pool_template_conversion_stall_failure_ratio{pool_id="0"} 7.5
pool_template_conversion_stall_window_candidates{kind="accepted",pool_id="0"} 38
pool_template_conversion_stall_window_candidates{kind="failed",pool_id="0"} 3
pool_template_conversion_stall_window_candidates{kind="total",pool_id="0"} 41
"""
        )

        sample = measurement.flatten_pool_metrics(metrics, latency_ms=2.5)

        self.assertEqual(sample["pool_active_connections"], 2)
        self.assertEqual(sample["pool_job_health_ready_miners"], 2)
        self.assertEqual(sample["pool_block_submit_accepted_total"], 38)
        self.assertEqual(sample["pool_block_submit_rejected_total"], 3)
        self.assertEqual(sample["pool_backend_mineable"], 1)
        self.assertEqual(sample["pool_backend_submit_ready"], 1)
        self.assertEqual(sample["pool_backend_p2p_mining_fresh"], 1)
        self.assertEqual(sample["pool_backend_p2p_fresh_consensus_peer_count"], 4)
        self.assertEqual(sample["pool_template_conversion_failure_ratio"], 7.5)
        self.assertEqual(sample["pool_template_conversion_window_total"], 41)

    def test_summarize_samples_reports_block_rate_and_worker_ranges(self) -> None:
        samples = [
            {
                "sampled_at": "2026-05-26T00:00:00+00:00",
                "sampled_epoch": 100,
                "source": "fixture",
                "overall": "syncing",
                "mode": "sync_only_no_miners",
                "sync_status": "syncing",
                "current_block": 1000,
                "remaining_blocks": 50,
                "connected_miners": 0,
                "managed_miners": 0,
                "collection_ms": 10.0,
                "chain_rpc_latency_ms_max": 5.0,
                "iowait_percent": 1.0,
                "adaptive_workers": {"global_rpc": 6},
                "host_profile": {"profile": "pi5", "os": "linux", "arch": "arm64"},
                "pool_active_connections": 2,
                "pool_job_health_ready_miners": 2,
                "pool_backend_p2p_mining_fresh": 1,
                "pool_backend_p2p_fresh_consensus_peer_count": 4,
                "pool_block_submit_accepted_total": 10,
                "pool_block_submit_rejected_total": 3,
                "pool_blocks_found_total": 13,
                "pool_shares_accepted_total": 100,
                "pool_shares_rejected_total": 10,
                "pool_template_conversion_failure_ratio": 7.5,
            },
            {
                "sampled_at": "2026-05-26T00:00:10+00:00",
                "sampled_epoch": 110,
                "source": "fixture",
                "overall": "ok",
                "mode": "ready_no_miners",
                "sync_status": "synced",
                "current_block": 1020,
                "remaining_blocks": 0,
                "connected_miners": 0,
                "managed_miners": 0,
                "collection_ms": 20.0,
                "chain_rpc_latency_ms_max": 7.0,
                "iowait_percent": 2.0,
                "adaptive_workers": {"global_rpc": 3},
                "host_profile": {"profile": "pi5", "os": "linux", "arch": "arm64"},
                "pool_active_connections": 2,
                "pool_job_health_ready_miners": 1,
                "pool_backend_p2p_mining_fresh": 1,
                "pool_backend_p2p_fresh_consensus_peer_count": 3,
                "pool_block_submit_accepted_total": 18,
                "pool_block_submit_rejected_total": 4,
                "pool_blocks_found_total": 22,
                "pool_shares_accepted_total": 140,
                "pool_shares_rejected_total": 17,
                "pool_template_conversion_failure_ratio": 9.5,
            },
        ]

        summary = measurement.summarize_samples(samples)

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["block_delta"], 20)
        self.assertEqual(summary["blocks_per_second"], 2.0)
        self.assertEqual(summary["chain_rpc_latency_ms_p95"], 7.0)
        self.assertEqual(summary["adaptive_worker_ranges"]["global_rpc"], {"min": 3, "max": 6})
        self.assertEqual(summary["pool_block_submit_accepted_delta"], 8)
        self.assertEqual(summary["pool_block_submit_rejected_delta"], 1)
        self.assertEqual(summary["pool_blocks_found_delta"], 9)
        self.assertEqual(summary["pool_shares_accepted_delta"], 40)
        self.assertEqual(summary["pool_shares_rejected_delta"], 7)
        self.assertEqual(summary["pool_ready_miners_min"], 1)
        self.assertEqual(summary["pool_fresh_consensus_peers_min"], 3)
        self.assertEqual(summary["pool_template_conversion_failure_ratio_max"], 9.5)


if __name__ == "__main__":
    unittest.main()
