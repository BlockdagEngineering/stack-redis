#!/usr/bin/env python3

import json
import pathlib
import sys
import unittest

OPS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS_DIR))

import pipeline_profiler as profiler  # noqa: E402


class PipelineProfilerTests(unittest.TestCase):
    def test_global_paid_rows_are_normalized_by_x100_count(self) -> None:
        payload = {
            "updated_at": "Jun 21, 2026 14:26:44 SAST",
            "rows": [
                {"key": "0x1719e0ee598c15957448d5e568948101df78e7a0", "pool": "0x1719...e7a0", "blocks": "76", "local": "true"},
                {"key": "0xd5f8df0a60bc1ff4636250b2a2dff319bf79b1f5", "pool": "0xd5f8...b1f5", "blocks": "110"},
                {"key": "0x94390581d27ac0faf4792984068e9a4366e3ebe0", "pool": "0x9439...ebe0", "blocks": "51"},
            ],
        }

        compact = profiler.compact_global_paid(payload, 1.2, None)

        rows = {row["pool"]: row for row in compact["tracked_rows"]}
        self.assertEqual(rows["0x1719...e7a0"]["x100_count"], 4)
        self.assertEqual(rows["0xd5f8...b1f5"]["x100_count"], 2)
        self.assertEqual(rows["0x9439...ebe0"]["x100_count"], 1)
        self.assertEqual(rows["0x1719...e7a0"]["blocks_per_x100"], 19)
        self.assertEqual(rows["0xd5f8...b1f5"]["blocks_per_x100"], 55)
        self.assertAlmostEqual(compact["local_vs_benchmarks"]["b1f5"]["local_vs_benchmark_rate"], 0.345455)

    def test_parse_psql_json_ignores_noise(self) -> None:
        payload = {"accepted": 10, "job_age_ms": {"p95": 2500}}

        parsed = profiler.parse_psql_json("psql banner\n" + json.dumps(payload) + "\n")

        self.assertEqual(parsed, payload)

    def test_compact_metrics_extracts_timing_pipeline_fields(self) -> None:
        metrics = """
pool_job_health_ready_miners{pool_id="0"} 4
pool_job_health_max_current_job_age_seconds{pool_id="0"} 0.296
pool_block_submit_outcomes_total{outcome="accepted",pool_id="0",reason="ok"} 100
pool_block_submit_outcomes_total{outcome="rejected",pool_id="0",reason="tip-overdue"} 7
pool_rpc_backend_node_health_submit_ready{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_p2p_mining_fresh{node="node",pool_id="0"} 1
pool_rpc_backend_node_health_template_invalidations_total{cause="state-changed",node="node",pool_id="0"} 11
pool_template_fetch_duration_seconds_sum{pool_id="0"} 4
pool_template_fetch_duration_seconds_count{pool_id="0"} 8
pool_rpc_backend_submit_duration_seconds_sum{node="node",pool_id="0",result="accepted"} 2
pool_rpc_backend_submit_duration_seconds_count{node="node",pool_id="0",result="accepted"} 4
pool_block_candidate_reject_job_age_seconds_sum{node="node",pool_id="0",reason="stale-job"} 10
pool_block_candidate_reject_job_age_seconds_count{node="node",pool_id="0",reason="stale-job"} 2
"""

        compact = profiler.compact_metrics(metrics, 2.0, None)

        self.assertEqual(compact["ready_miners"], 4)
        self.assertEqual(compact["current_job_age_seconds_max"], 0.296)
        self.assertEqual(compact["submit_accepted_total"], 100)
        self.assertEqual(compact["submit_rejected_by_reason"], {"tip-overdue": 7})
        self.assertEqual(compact["template_invalidations_by_cause"], {"state-changed": 11})
        self.assertEqual(compact["template_fetch_duration"]["total"]["avg_seconds"], 0.5)
        self.assertEqual(compact["rpc_submit_duration_by_result"]["accepted"]["avg_seconds"], 0.5)
        self.assertEqual(compact["candidate_reject_job_age_by_reason"]["stale-job"]["avg_seconds"], 5.0)

    def test_summary_reports_counter_deltas_and_job_age_risk(self) -> None:
        samples = [
            {
                "sampled_at": "a",
                "sampled_epoch": 100,
                "metrics": {
                    "submit_accepted_total": 10,
                    "submit_rejected_total": 2,
                    "submit_rejected_by_reason": {"tip-overdue": 2},
                    "template_broadcasts_total": 20,
                    "template_invalidations_by_cause": {"state-changed": 1},
                    "ready_miners": 4,
                    "backend_submit_ready": 1,
                    "backend_p2p_fresh": 1,
                },
                "db_submission_timing": {"job_age_ms": {"p95": 1000}},
            },
            {
                "sampled_at": "b",
                "sampled_epoch": 160,
                "metrics": {
                    "submit_accepted_total": 25,
                    "submit_rejected_total": 6,
                    "submit_rejected_by_reason": {"tip-overdue": 4, "stale-job": 2},
                    "template_broadcasts_total": 45,
                    "template_invalidations_by_cause": {"state-changed": 5},
                    "ready_miners": 0,
                    "backend_submit_ready": 0,
                    "backend_p2p_fresh": 1,
                },
                "db_submission_timing": {"job_age_ms": {"p95": 38000}},
            },
        ]

        summary = profiler.summarize_samples(samples)

        self.assertEqual(summary["accepted_submit_delta"], 15)
        self.assertEqual(summary["rejected_submit_delta"], 4)
        self.assertEqual(summary["submit_rejected_by_reason_delta"], {"stale-job": 2, "tip-overdue": 2})
        self.assertEqual(summary["template_broadcast_delta"], 25)
        self.assertEqual(summary["template_invalidations_by_cause_delta"], {"state-changed": 4})
        self.assertEqual(summary["ready_miners_min"], 0)
        self.assertEqual(summary["backend_submit_ready_min"], 0)
        self.assertEqual(summary["db_job_age_p95_ms_max"], 38000)


if __name__ == "__main__":
    unittest.main()
