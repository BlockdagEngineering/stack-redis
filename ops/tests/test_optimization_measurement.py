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
            "can_accept_shares": True,
            "can_submit_blocks": False,
            "age_seconds": 2.0,
            "fresh": True,
            "status_sampler": {"hit": True, "age_seconds": 1.5},
            "sync_progress": {
                "status": "syncing",
                "current_block": 10,
                "highest_block": 15,
                "current_block_source": "eth_syncing",
                "remaining_blocks": 5,
                "native_is_current": True,
                "chain_syncing": True,
                "mining_advisory_sync": True,
                "p2p_connections": 8,
                "p2p_network_gap": 0,
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
        self.assertEqual(sample["current_block_source"], "eth_syncing")
        self.assertEqual(sample["remaining_blocks"], 5)
        self.assertTrue(sample["native_is_current"])
        self.assertTrue(sample["chain_syncing"])
        self.assertTrue(sample["mining_advisory_sync"])
        self.assertEqual(sample["p2p_connections"], 8)
        self.assertEqual(sample["p2p_network_gap"], 0)
        self.assertTrue(sample["can_accept_shares"])
        self.assertFalse(sample["can_submit_blocks"])
        self.assertEqual(sample["chain_rpc_latency_ms_max"], 12.5)
        self.assertEqual(sample["adaptive_workers"]["global_rpc"], 6)
        self.assertEqual(sample["dashboard_latency_ms"], 3.1)
        self.assertEqual(sample["status_age_seconds"], 2.0)
        self.assertTrue(sample["status_fresh"])
        self.assertTrue(sample["status_sampler_hit"])
        self.assertEqual(sample["status_sampler_age_seconds"], 1.5)

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
pool_shares_rejected_total{pool_id="0",reason="non_current_job"} 4
pool_rpc_backend_node_health_mineable{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_submit_ready{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_mining_fresh{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_fresh_consensus_peer_count{node="node",pool_id="0"} 4
pool_rpc_backend_node_health_template_invalidations_total{cause="parent-changed",node="node",pool_id="0"} 5
pool_clean_template_refresh_events_total{event="broadcast",pool_id="0"} 8
pool_clean_template_refresh_events_total{event="readiness_hold",pool_id="0"} 2
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
        self.assertEqual(sample["pool_block_submit_rejected_by_reason"], {"stale-parent": 2, "tip-overdue": 1})
        self.assertEqual(sample["pool_share_reject_by_reason"], {"invalidated_job": 38, "non_current_job": 4})
        self.assertEqual(sample["pool_backend_mineable"], 1)
        self.assertEqual(sample["pool_backend_submit_ready"], 1)
        self.assertEqual(sample["pool_backend_p2p_mining_fresh"], 1)
        self.assertEqual(sample["pool_backend_p2p_fresh_consensus_peer_count"], 4)
        self.assertEqual(sample["pool_template_invalidation_by_cause"], {"parent-changed": 5})
        self.assertEqual(sample["pool_clean_refresh_by_event"], {"broadcast": 8, "readiness_hold": 2})
        self.assertEqual(sample["pool_template_conversion_failure_ratio"], 7.5)
        self.assertEqual(sample["pool_template_conversion_window_total"], 41)

    def test_flatten_status_sample_infers_current_block_source(self) -> None:
        payload = {
            "sync_progress": {
                "current_block": 42,
                "highest_block": 50,
                "nodes": {
                    "node": {
                        "current_block": 42,
                        "current_block_source": "eth_syncing",
                    }
                },
            },
            "adaptive_concurrency": {"workers": {}},
        }

        sample = measurement.flatten_status_sample(payload, "fixture", 1.0)

        self.assertEqual(sample["current_block"], 42)
        self.assertEqual(sample["current_block_source"], "eth_syncing")

    def test_flatten_status_sample_marks_native_chain_count_source(self) -> None:
        payload = {
            "sync_progress": {
                "current_block": 121,
                "highest_block": 121,
                "chain_block_count": 121,
                "native_is_current": True,
                "source": "native-rpc",
            },
            "adaptive_concurrency": {"workers": {}},
        }

        sample = measurement.flatten_status_sample(payload, "fixture", 1.0)

        self.assertEqual(sample["current_block"], 121)
        self.assertEqual(sample["current_block_source"], "native-rpc")

    def test_summarize_samples_reports_block_rate_and_worker_ranges(self) -> None:
        samples = [
            {
                "sampled_at": "2026-05-26T00:00:00+00:00",
                "sampled_epoch": 100,
                "source": "fixture",
                "overall": "syncing",
                "mode": "sync_only_no_miners",
                "can_mine": False,
                "can_submit_blocks": False,
                "sync_status": "syncing",
                "current_block": 1000,
                "current_block_source": "native",
                "remaining_blocks": 50,
                "native_is_current": False,
                "chain_syncing": True,
                "mining_advisory_sync": False,
                "p2p_connections": 6,
                "p2p_network_gap": 3,
                "connected_miners": 0,
                "managed_miners": 0,
                "collection_ms": 10.0,
                "status_age_seconds": 1.0,
                "status_sampler_hit": True,
                "chain_rpc_latency_ms_max": 5.0,
                "iowait_percent": 1.0,
                "adaptive_workers": {"global_rpc": 6},
                "host_profile": {"profile": "pi5", "os": "linux", "arch": "arm64"},
                "pool_active_connections": 2,
                "pool_job_health_ready_miners": 2,
                "pool_backend_mineable": 1,
                "pool_backend_submit_ready": 1,
                "pool_backend_p2p_mining_fresh": 1,
                "pool_backend_p2p_fresh_consensus_peer_count": 4,
                "pool_backend_p2p_best_peer_lead_blocks": 2,
                "pool_block_submit_accepted_total": 10,
                "pool_block_submit_rejected_total": 3,
                "pool_block_submit_rejected_by_reason": {"tip-overdue": 2, "stale-job": 1},
                "pool_blocks_found_total": 13,
                "pool_shares_accepted_total": 100,
                "pool_shares_rejected_total": 10,
                "pool_share_reject_by_reason": {"invalidated_job": 7, "non_current_job": 3},
                "pool_template_invalidation_by_cause": {"parent-changed": 4},
                "pool_clean_refresh_by_event": {"broadcast": 8, "readiness_hold": 1},
                "pool_template_conversion_failure_ratio": 7.5,
            },
            {
                "sampled_at": "2026-05-26T00:00:10+00:00",
                "sampled_epoch": 110,
                "source": "fixture",
                "overall": "ok",
                "mode": "ready_no_miners",
                "can_mine": True,
                "can_submit_blocks": True,
                "sync_status": "synced",
                "current_block": 1020,
                "current_block_source": "native",
                "remaining_blocks": 0,
                "native_is_current": True,
                "chain_syncing": True,
                "mining_advisory_sync": True,
                "p2p_connections": 8,
                "p2p_network_gap": 0,
                "connected_miners": 0,
                "managed_miners": 0,
                "collection_ms": 20.0,
                "status_age_seconds": 3.0,
                "status_sampler_hit": False,
                "chain_rpc_latency_ms_max": 7.0,
                "iowait_percent": 2.0,
                "adaptive_workers": {"global_rpc": 3},
                "host_profile": {"profile": "pi5", "os": "linux", "arch": "arm64"},
                "pool_active_connections": 2,
                "pool_job_health_ready_miners": 1,
                "pool_backend_mineable": 1,
                "pool_backend_submit_ready": 0,
                "pool_backend_p2p_mining_fresh": 1,
                "pool_backend_p2p_fresh_consensus_peer_count": 3,
                "pool_backend_p2p_best_peer_lead_blocks": 0,
                "pool_block_submit_accepted_total": 18,
                "pool_block_submit_rejected_total": 4,
                "pool_block_submit_rejected_by_reason": {"tip-overdue": 3, "stale-job": 1},
                "pool_blocks_found_total": 22,
                "pool_shares_accepted_total": 140,
                "pool_shares_rejected_total": 17,
                "pool_share_reject_by_reason": {"invalidated_job": 11, "non_current_job": 6},
                "pool_template_invalidation_by_cause": {"parent-changed": 9},
                "pool_clean_refresh_by_event": {"broadcast": 13, "readiness_hold": 2},
                "pool_template_conversion_failure_ratio": 9.5,
            },
        ]

        summary = measurement.summarize_samples(samples)

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["block_delta"], 20)
        self.assertTrue(summary["block_delta_valid"])
        self.assertEqual(summary["blocks_per_second"], 2.0)
        self.assertEqual(summary["current_block_source_first"], "native")
        self.assertEqual(summary["current_block_source_last"], "native")
        self.assertEqual(summary["can_submit_blocks_values"], ["false", "true"])
        self.assertEqual(summary["native_is_current_values"], ["false", "true"])
        self.assertEqual(summary["chain_syncing_values"], ["true"])
        self.assertEqual(summary["mining_advisory_sync_values"], ["false", "true"])
        self.assertEqual(summary["p2p_connections_min"], 6)
        self.assertEqual(summary["p2p_network_gap_max"], 3)
        self.assertEqual(summary["chain_rpc_latency_ms_p95"], 7.0)
        self.assertEqual(summary["adaptive_worker_ranges"]["global_rpc"], {"min": 3, "max": 6})
        self.assertEqual(summary["pool_backend_mineable_min"], 1)
        self.assertEqual(summary["pool_backend_submit_ready_min"], 0)
        self.assertEqual(summary["pool_backend_peer_lead_max"], 2)
        self.assertEqual(summary["pool_block_submit_accepted_delta"], 8)
        self.assertEqual(summary["pool_block_submit_rejected_delta"], 1)
        self.assertEqual(summary["pool_block_submit_rejected_per_accepted"], 0.125)
        self.assertEqual(summary["pool_block_submit_rejected_by_reason_delta"], {"tip-overdue": 1})
        self.assertEqual(summary["pool_accepted_blocks_per_hour"], 2880.0)
        self.assertEqual(summary["pool_blocks_found_delta"], 9)
        self.assertEqual(summary["pool_shares_accepted_delta"], 40)
        self.assertEqual(summary["pool_shares_rejected_delta"], 7)
        self.assertEqual(summary["pool_share_reject_ratio"], 0.148936)
        self.assertEqual(summary["pool_share_reject_by_reason_delta"], {"invalidated_job": 4, "non_current_job": 3})
        self.assertEqual(summary["pool_template_invalidation_by_cause_delta"], {"parent-changed": 5})
        self.assertEqual(summary["pool_clean_refresh_by_event_delta"], {"broadcast": 5, "readiness_hold": 1})
        self.assertEqual(summary["pool_ready_miners_min"], 1)
        self.assertEqual(summary["pool_fresh_consensus_peers_min"], 3)
        self.assertEqual(summary["pool_template_conversion_failure_ratio_max"], 9.5)
        self.assertEqual(summary["status_age_seconds_p95"], 3.0)
        self.assertEqual(summary["status_age_seconds_max"], 3.0)
        self.assertEqual(summary["status_sampler_hit_values"], ["false", "true"])

    def test_collect_status_sample_limits_local_status_cache_age(self) -> None:
        original_collect_status_cached = measurement.collect_status_cached
        original_collect_pool_metrics_sample = measurement.collect_pool_metrics_sample
        calls = {}

        def fake_collect_status_cached(*, include_logs, max_age_seconds):
            calls["include_logs"] = include_logs
            calls["max_age_seconds"] = max_age_seconds
            return {
                "overall": "ok",
                "mode": "mining",
                "can_mine": True,
                "can_accept_shares": True,
                "can_submit_blocks": True,
                "sync_progress": {"status": "synced"},
                "adaptive_concurrency": {"workers": {}},
            }

        try:
            measurement.collect_status_cached = fake_collect_status_cached
            measurement.collect_pool_metrics_sample = lambda _url, _timeout: {}
            sample = measurement.collect_status_sample(
                status_url=None,
                timeout=1.0,
                pool_metrics_url=None,
                local_status_max_age_seconds=2.5,
            )
        finally:
            measurement.collect_status_cached = original_collect_status_cached
            measurement.collect_pool_metrics_sample = original_collect_pool_metrics_sample

        self.assertEqual(calls["include_logs"], False)
        self.assertEqual(calls["max_age_seconds"], 2.5)
        self.assertEqual(sample["source"], "local-collector")
        self.assertTrue(sample["can_submit_blocks"])

    def test_summarize_samples_marks_mixed_block_sources_untrusted(self) -> None:
        samples = [
            {
                "sampled_at": "2026-05-26T00:00:00+00:00",
                "sampled_epoch": 100,
                "source": "fixture",
                "current_block": 2000,
                "current_block_source": "eth_syncing",
                "adaptive_workers": {},
            },
            {
                "sampled_at": "2026-05-26T00:00:10+00:00",
                "sampled_epoch": 110,
                "source": "fixture",
                "current_block": 1995,
                "current_block_source": "native",
                "adaptive_workers": {},
            },
        ]

        summary = measurement.summarize_samples(samples)

        self.assertIsNone(summary["block_delta"])
        self.assertFalse(summary["block_delta_valid"])
        self.assertEqual(summary["block_delta_warning"], "current_block source missing, changed, or moved backwards")
        self.assertIsNone(summary["blocks_per_second"])

    def test_summarize_samples_rejects_missing_block_sources(self) -> None:
        samples = [
            {
                "sampled_at": "2026-05-26T00:00:00+00:00",
                "sampled_epoch": 100,
                "source": "fixture",
                "current_block": 2000,
                "adaptive_workers": {},
            },
            {
                "sampled_at": "2026-05-26T00:00:10+00:00",
                "sampled_epoch": 110,
                "source": "fixture",
                "current_block": 2010,
                "adaptive_workers": {},
            },
        ]

        summary = measurement.summarize_samples(samples)

        self.assertIsNone(summary["block_delta"])
        self.assertFalse(summary["block_delta_valid"])
        self.assertEqual(summary["block_delta_warning"], "current_block source missing, changed, or moved backwards")
        self.assertIsNone(summary["blocks_per_second"])


if __name__ == "__main__":
    unittest.main()
