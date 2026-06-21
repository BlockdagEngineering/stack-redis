#!/usr/bin/env python3
"""Profile the live chain -> pool -> ASIC -> pool -> chain timing pipeline.

This collector is intentionally read-only. It stores enough correlated timing
evidence to compare code/config states against paid-block conversion instead of
optimizing from one metric in isolation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from optimization_measurement import (
    metric_max,
    metric_sum,
    metric_sum_by_label,
    parse_prometheus_metrics,
)
from pool_ops import RUNTIME_DIR, now_iso, seconds_since_epoch


DEFAULT_STATUS_URL = "http://127.0.0.1:8088/api/status"
DEFAULT_GLOBAL_PAID_URL = "http://127.0.0.1:8088/api/live/global-pool-earnings"
DEFAULT_POOL_METRICS_URL = "http://127.0.0.1:9090/metrics"
DEFAULT_JOB_STATE_URL = "http://127.0.0.1:9090/health/job-state"
DEFAULT_ASIC_PERFORMANCE_URL = "http://127.0.0.1:9090/health/asic-performance"
DEFAULT_OUTPUT_DIR = RUNTIME_DIR / "profiling"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

POOL_X100_COUNTS = {
    "0x1719e0ee598c15957448d5e568948101df78e7a0": 4,
    "0x1719...e7a0": 4,
    "0xd5f8df0a60bc1ff4636250b2a2dff319bf79b1f5": 2,
    "0xd5f8...b1f5": 2,
    "0x94390581d27ac0faf4792984068e9a4366e3ebe0": 1,
    "0x9439...ebe0": 1,
}
LOCAL_POOL = "0x1719e0ee598c15957448d5e568948101df78e7a0"
BENCHMARK_POOLS = {
    "b1f5": "0xd5f8df0a60bc1ff4636250b2a2dff319bf79b1f5",
    "ebe0": "0x94390581d27ac0faf4792984068e9a4366e3ebe0",
}

NODE_LOG_PATTERNS = (
    "Rewinding blockchain",
    "Recovered mining template",
    "broadcast block failed",
    "nonce too low",
    "nonce too high",
    "request error",
)
POOL_LOG_PATTERNS = (
    "Block submitted successfully",
    "Block submission too late",
    "template refresh backend not ready",
    "node template invalidation",
    "STALE JOB",
    "duplicate",
    "stale-parent",
    "tip-overdue",
    "node-syncing",
    "invalidated 4 current miner jobs",
    "preserving current jobs",
)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def run_cmd(command: list[str], *, cwd: Path = PROJECT_ROOT, timeout: float = 10.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - profiler should continue.
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
    }


def fetch_json(url: str, timeout: float = 5.0) -> tuple[dict[str, Any], float | None, str | None]:
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}, round((time.monotonic() - started) * 1000, 3), None
    except Exception as exc:  # noqa: BLE001
        return {}, round((time.monotonic() - started) * 1000, 3), str(exc)


def fetch_text(url: str, timeout: float = 5.0) -> tuple[str, float | None, str | None]:
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"accept": "text/plain"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace"), round((time.monotonic() - started) * 1000, 3), None
    except Exception as exc:  # noqa: BLE001
        return "", round((time.monotonic() - started) * 1000, 3), str(exc)


def metric_rows(metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float], name: str) -> list[tuple[dict[str, str], float]]:
    return [(dict(labels), value) for (metric_name, labels), value in metrics.items() if metric_name == name]


def histogram_average_by_label(
    metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    base_name: str,
    group_label: str | None = None,
) -> dict[str, dict[str, float]]:
    sums: dict[str, float] = {}
    counts: dict[str, float] = {}
    for labels, value in metric_rows(metrics, base_name + "_sum"):
        key = labels.get(group_label, "total") if group_label else "total"
        sums[key] = sums.get(key, 0.0) + value
    for labels, value in metric_rows(metrics, base_name + "_count"):
        key = labels.get(group_label, "total") if group_label else "total"
        counts[key] = counts.get(key, 0.0) + value
    out: dict[str, dict[str, float]] = {}
    for key in sorted(set(sums) | set(counts)):
        count = counts.get(key, 0.0)
        total = sums.get(key, 0.0)
        out[key] = {
            "count": round(count, 6),
            "sum_seconds": round(total, 6),
            "avg_seconds": round(total / count, 6) if count > 0 else 0.0,
        }
    return out


def compact_metrics(text: str, latency_ms: float | None, error: str | None) -> dict[str, Any]:
    metrics = parse_prometheus_metrics(text) if text else {}
    rejected = 0.0
    for labels, value in metric_rows(metrics, "pool_block_submit_outcomes_total"):
        if labels.get("outcome") != "accepted":
            rejected += value
    return {
        "latency_ms": latency_ms,
        "error": error,
        "active_connections": metric_sum(metrics, "pool_active_connections"),
        "authorized_miners": metric_sum(metrics, "pool_job_health_authorized_miners"),
        "ready_miners": metric_sum(metrics, "pool_job_health_ready_miners"),
        "current_job_age_seconds_max": metric_max(metrics, "pool_job_health_max_current_job_age_seconds"),
        "current_job_invalidated_miners": metric_sum(metrics, "pool_job_health_current_job_invalidated_miners"),
        "current_job_stale_miners": metric_sum(metrics, "pool_job_health_current_job_stale_miners"),
        "current_job_expired_miners": metric_sum(metrics, "pool_job_health_current_job_expired_miners"),
        "template_broadcasts_total": metric_sum(metrics, "pool_template_broadcasts_total"),
        "submit_accepted_total": metric_sum(metrics, "pool_block_submit_outcomes_total", {"outcome": "accepted"}),
        "submit_rejected_total": round(rejected, 6),
        "submit_rejected_by_reason": metric_sum_by_label(
            metrics,
            "pool_block_submit_outcomes_total",
            "reason",
            exclude_labels={"outcome": "accepted"},
        ),
        "shares_accepted_total": metric_sum(metrics, "pool_shares_accepted_total"),
        "shares_rejected_total": metric_sum(metrics, "pool_shares_rejected_total"),
        "backend_mineable": metric_max(metrics, "pool_rpc_backend_node_health_mineable"),
        "backend_submit_ready": metric_max(metrics, "pool_rpc_backend_node_health_submit_ready"),
        "backend_p2p_fresh": metric_max(metrics, "pool_rpc_backend_node_health_p2p_mining_fresh"),
        "backend_consensus_peers": metric_max(metrics, "pool_rpc_backend_node_health_p2p_consensus_peer_count"),
        "backend_fresh_consensus_peers": metric_max(metrics, "pool_rpc_backend_node_health_p2p_fresh_consensus_peer_count"),
        "backend_best_peer_lead_blocks": metric_max(metrics, "pool_rpc_backend_node_health_p2p_best_peer_lead_blocks"),
        "backend_best_peer_graph_state_age_seconds": metric_max(
            metrics,
            "pool_rpc_backend_node_health_p2p_best_peer_graph_state_age_seconds",
        ),
        "backend_template_age_seconds": metric_max(metrics, "pool_rpc_backend_node_health_template_age_seconds"),
        "backend_template_sequence": metric_max(metrics, "pool_rpc_backend_node_health_template_sequence"),
        "backend_last_template_build_age_seconds": metric_max(
            metrics,
            "pool_rpc_backend_node_health_last_template_build_age_seconds",
        ),
        "backend_last_template_build_duration_seconds": metric_max(
            metrics,
            "pool_rpc_backend_node_health_last_template_build_duration_seconds",
        ),
        "backend_pending_template_build": metric_max(metrics, "pool_rpc_backend_node_health_pending_template_build"),
        "backend_pending_template_invalidation_by_cause": metric_sum_by_label(
            metrics,
            "pool_rpc_backend_node_health_pending_template_invalidation",
            "cause",
        ),
        "template_invalidations_by_cause": metric_sum_by_label(
            metrics,
            "pool_rpc_backend_node_health_template_invalidations_total",
            "cause",
        ),
        "template_conversion_failure_ratio": metric_max(metrics, "pool_template_conversion_stall_failure_ratio"),
        "template_conversion_window": metric_sum_by_label(
            metrics,
            "pool_template_conversion_stall_window_candidates",
            "kind",
        ),
        "timing_controller_job_age_ms": metric_max(metrics, "pool_block_timing_controller_job_age_ms"),
        "timing_controller_template_ttl_ms": metric_max(metrics, "pool_block_timing_controller_template_ttl_ms"),
        "timing_controller_stale_grace_ms": metric_max(metrics, "pool_block_timing_controller_recent_stale_grace_ms"),
        "template_fetch_duration": histogram_average_by_label(metrics, "pool_template_fetch_duration_seconds"),
        "rpc_submit_duration_by_result": histogram_average_by_label(
            metrics,
            "pool_rpc_backend_submit_duration_seconds",
            "result",
        ),
        "candidate_reject_job_age_by_reason": histogram_average_by_label(
            metrics,
            "pool_block_candidate_reject_job_age_seconds",
            "reason",
        ),
    }


def compact_status(status: dict[str, Any], latency_ms: float | None, error: str | None) -> dict[str, Any]:
    sync = status.get("sync_progress") if isinstance(status.get("sync_progress"), dict) else {}
    pool = status.get("pool_health") if isinstance(status.get("pool_health"), dict) else {}
    miner = status.get("miner_health") if isinstance(status.get("miner_health"), dict) else {}
    return {
        "latency_ms": latency_ms,
        "error": error,
        "overall": status.get("overall"),
        "mode": status.get("mode"),
        "can_accept_shares": status.get("can_accept_shares"),
        "can_submit_blocks": status.get("can_submit_blocks"),
        "sync_status": sync.get("status"),
        "native_is_current": sync.get("native_is_current"),
        "chain_syncing": sync.get("chain_syncing"),
        "mining_advisory_sync": sync.get("mining_advisory_sync"),
        "current_block": sync.get("current_block"),
        "highest_block": sync.get("highest_block"),
        "chain_block_count": sync.get("chain_block_count"),
        "p2p_connections": sync.get("p2p_connections") or sync.get("peer_count"),
        "p2p_network_gap": sync.get("p2p_network_gap"),
        "best_peer_mainorder": sync.get("best_peer_mainorder"),
        "peer_mainorder_gap": sync.get("peer_mainorder_gap"),
        "pool_source_job_health": pool.get("source_job_health"),
        "miner_connected_count": miner.get("connected_count"),
        "miner_managed_count": miner.get("managed_count"),
        "miner_tracked_count": miner.get("tracked_count"),
    }


def compact_job_state(job_state: dict[str, Any], latency_ms: float | None, error: str | None) -> dict[str, Any]:
    clients = job_state.get("clients") if isinstance(job_state.get("clients"), list) else []
    compact_clients = []
    for client in clients:
        if not isinstance(client, dict):
            continue
        compact_clients.append(
            {
                "mac": client.get("asic_mac") or client.get("mac"),
                "worker": client.get("worker"),
                "ready": client.get("ready"),
                "health": client.get("health"),
                "current_job_age_ms": client.get("current_job_age_ms"),
                "current_job_id": client.get("current_job_id"),
                "protocol_variant": client.get("protocol_variant"),
            }
        )
    return {
        "latency_ms": latency_ms,
        "error": error,
        "status": job_state.get("status"),
        "active_connections": job_state.get("active_connections"),
        "authorized_connections": job_state.get("authorized_connections"),
        "subscribed_connections": job_state.get("subscribed_connections"),
        "ready_connections": job_state.get("ready_connections"),
        "clients": compact_clients,
    }


def compact_asic_performance(payload: dict[str, Any], latency_ms: float | None, error: str | None) -> dict[str, Any]:
    lanes = payload.get("lanes") if isinstance(payload.get("lanes"), list) else []
    compact_lanes = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        compact_lanes.append(
            {
                "lane_id": lane.get("lane_id"),
                "asic_mac": lane.get("asic_mac"),
                "remote_host": lane.get("remote_host"),
                "worker": lane.get("worker"),
                "ready": lane.get("ready"),
                "health": lane.get("health"),
                "current_job_age_ms": lane.get("current_job_age_ms"),
                "pdiff": lane.get("pdiff"),
                "protocol_variant": lane.get("protocol_variant"),
                "blocks_30m": lane.get("blocks_30m"),
                "rejected_30m": lane.get("rejected_30m"),
                "rejected_local_30m": lane.get("rejected_local_30m"),
                "last_accepted_unix_ms": lane.get("last_accepted_unix_ms"),
            }
        )
    return {
        "latency_ms": latency_ms,
        "error": error,
        "generated_at_unix_ms": payload.get("generated_at_unix_ms"),
        "window_seconds": payload.get("window_seconds"),
        "bucket_seconds": payload.get("bucket_seconds"),
        "lanes": compact_lanes,
    }


def pool_x100_count(row: dict[str, Any]) -> int | None:
    keys = [
        str(row.get("key") or "").lower(),
        str(row.get("pool") or "").lower(),
        str(row.get("address") or "").lower(),
    ]
    for key in keys:
        if key in POOL_X100_COUNTS:
            return POOL_X100_COUNTS[key]
    for key in keys:
        for known, count in POOL_X100_COUNTS.items():
            if key and (key.endswith(known[-4:]) or known.endswith(key[-4:])):
                return count
    return None


def parse_block_count(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None


def compact_global_paid(payload: dict[str, Any], latency_ms: float | None, error: str | None) -> dict[str, Any]:
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    tracked = []
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        x100 = pool_x100_count(row)
        if not x100:
            continue
        key = str(row.get("key") or row.get("pool") or "").lower()
        blocks = parse_block_count(row.get("blocks"))
        entry = {
            "key": key,
            "pool": row.get("pool"),
            "blocks": blocks,
            "work": row.get("work"),
            "x100_count": x100,
            "blocks_per_x100": round(blocks / x100, 6) if blocks is not None and x100 > 0 else None,
            "local": str(row.get("local")).lower() == "true",
            "last": row.get("last"),
        }
        tracked.append(entry)
        if key:
            by_key[key] = entry
    local = next((row for row in tracked if row["key"] == LOCAL_POOL or row["local"]), None)
    benchmark_ratios: dict[str, Any] = {}
    if local and local.get("blocks") is not None:
        local_blocks = float(local["blocks"])
        local_x100 = float(local["x100_count"] or 0)
        for name, full_key in BENCHMARK_POOLS.items():
            benchmark = by_key.get(full_key)
            if not benchmark or benchmark.get("blocks_per_x100") in (None, 0):
                continue
            expected = float(benchmark["blocks_per_x100"]) * local_x100
            benchmark_ratios[name] = {
                "benchmark_blocks_per_x100": benchmark["blocks_per_x100"],
                "local_expected_blocks_at_benchmark_rate": round(expected, 6),
                "local_vs_benchmark_rate": round(local_blocks / expected, 6) if expected > 0 else None,
            }
    return {
        "latency_ms": latency_ms,
        "error": error,
        "updated_at": payload.get("updated_at"),
        "title": payload.get("title"),
        "tracked_rows": tracked,
        "local_vs_benchmarks": benchmark_ratios,
    }


def submission_timing_sql(window_seconds: int) -> str:
    window_seconds = max(1, int(window_seconds))
    return f"""
WITH rows AS (
  SELECT *
  FROM block_submissions
  WHERE created_at >= now() - interval '{window_seconds} seconds'
),
outcomes AS (
  SELECT
    concat(CASE WHEN accepted THEN 'accepted' ELSE 'rejected' END, ':', coalesce(outcome, 'unknown')) AS key,
    count(*) AS count
  FROM rows
  GROUP BY 1
),
asic AS (
  SELECT
    coalesce(asic_mac, 'unknown') AS asic_mac,
    count(*) FILTER (WHERE accepted) AS accepted,
    count(*) FILTER (WHERE NOT accepted) AS rejected,
    round(avg(job_age_ms)::numeric, 3) AS job_age_ms_avg,
    round((percentile_cont(0.50) WITHIN GROUP (ORDER BY job_age_ms))::numeric, 3) AS job_age_ms_p50,
    round((percentile_cont(0.95) WITHIN GROUP (ORDER BY job_age_ms))::numeric, 3) AS job_age_ms_p95,
    max(job_age_ms) AS job_age_ms_max
  FROM rows
  WHERE job_age_ms IS NOT NULL
  GROUP BY 1
)
SELECT jsonb_build_object(
  'window_seconds', {window_seconds},
  'row_count', (SELECT count(*) FROM rows),
  'accepted', (SELECT count(*) FILTER (WHERE accepted) FROM rows),
  'rejected', (SELECT count(*) FILTER (WHERE NOT accepted) FROM rows),
  'job_age_ms', (
    SELECT jsonb_build_object(
      'avg', round(avg(job_age_ms)::numeric, 3),
      'p50', round((percentile_cont(0.50) WITHIN GROUP (ORDER BY job_age_ms))::numeric, 3),
      'p95', round((percentile_cont(0.95) WITHIN GROUP (ORDER BY job_age_ms))::numeric, 3),
      'max', max(job_age_ms)
    )
    FROM rows
    WHERE job_age_ms IS NOT NULL
  ),
  'by_outcome', coalesce((SELECT jsonb_object_agg(key, count) FROM outcomes), '{{}}'::jsonb),
  'by_asic', coalesce((
    SELECT jsonb_agg(
      jsonb_build_object(
        'asic_mac', asic_mac,
        'accepted', accepted,
        'rejected', rejected,
        'job_age_ms_avg', job_age_ms_avg,
        'job_age_ms_p50', job_age_ms_p50,
        'job_age_ms_p95', job_age_ms_p95,
        'job_age_ms_max', job_age_ms_max
      )
      ORDER BY asic_mac
    )
    FROM asic
  ), '[]'::jsonb)
)::text;
""".strip()


def parse_psql_json(text: str) -> dict[str, Any]:
    for raw in reversed(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    return {}


def collect_db_submission_timing(window_seconds: int, timeout: float) -> dict[str, Any]:
    result = run_cmd(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "pool-db",
            "psql",
            "-U",
            "bdag_pool",
            "-d",
            "bdagpool",
            "-t",
            "-A",
            "-c",
            submission_timing_sql(window_seconds),
        ],
        timeout=timeout,
    )
    payload = parse_psql_json(result.get("stdout") or "")
    payload["latency_ms"] = result.get("latency_ms")
    if not result.get("ok"):
        payload["error"] = (result.get("stderr") or result.get("stdout") or result.get("error") or "")[-2000:]
    return payload


def count_patterns(text: str, patterns: tuple[str, ...]) -> dict[str, int]:
    return {pattern: len(re.findall(re.escape(pattern), text)) for pattern in patterns}


def collect_log_counts(service: str, lookback_seconds: int, patterns: tuple[str, ...], timeout: float) -> dict[str, Any]:
    result = run_cmd(
        ["docker", "compose", "logs", f"--since={max(1, int(lookback_seconds))}s", "--no-color", service],
        timeout=timeout,
    )
    text = result.get("stdout") or ""
    return {
        "latency_ms": result.get("latency_ms"),
        "error": None if result.get("ok") else (result.get("stderr") or result.get("error") or "")[-1000:],
        "line_count": len(text.splitlines()),
        "counts": count_patterns(text, patterns),
    }


def collect_docker_stats(timeout: float) -> dict[str, Any]:
    result = run_cmd(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            "node",
            "pool",
            "dashboard",
            "postgres",
            "status-sampler",
        ],
        timeout=timeout,
    )
    rows = []
    for line in (result.get("stdout") or "").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {
        "latency_ms": result.get("latency_ms"),
        "error": None if result.get("ok") else (result.get("stderr") or result.get("error") or "")[-1000:],
        "rows": rows,
    }


def repo_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    branch = run_cmd(["git", "branch", "--show-current"], cwd=path, timeout=5)
    head = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=path, timeout=5)
    status = run_cmd(["git", "status", "--short"], cwd=path, timeout=5)
    return {
        "path": str(path),
        "exists": True,
        "branch": (branch.get("stdout") or "").strip(),
        "head": (head.get("stdout") or "").strip(),
        "dirty": bool((status.get("stdout") or "").strip()),
        "status": (status.get("stdout") or status.get("stderr") or "")[:4000],
    }


def write_manifest(session_dir: Path, args: argparse.Namespace) -> None:
    repos = {
        "stack_redis": PROJECT_ROOT,
        "pool": Path("/home/jeremy/blockdag-source/pool"),
        "blockdag_corechain": Path("/home/jeremy/blockdag-source/blockdag-corechain"),
        "redis_dash": Path("/home/jeremy/blockdag-source/redis-dash"),
    }
    manifest = {
        "document_type": "bdag_pipeline_profile_manifest",
        "generated_at": now_iso(),
        "label": args.label,
        "duration_seconds": args.duration_seconds,
        "interval_seconds": args.interval_seconds,
        "db_window_seconds": args.db_window_seconds,
        "log_lookback_seconds": args.log_lookback_seconds,
        "urls": {
            "status": args.status_url,
            "global_paid": args.global_paid_url,
            "pool_metrics": args.pool_metrics_url,
            "job_state": args.job_state_url,
            "asic_performance": args.asic_performance_url,
        },
        "benchmark_x100_counts": {
            "0x1719...e7a0": 4,
            "0xd5f8...b1f5": 2,
            "0x9439...ebe0": 1,
        },
        "repos": {name: repo_state(path) for name, path in repos.items()},
        "read_only": True,
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def counter_delta(first: dict[str, Any], last: dict[str, Any], key: str) -> float | None:
    first_value = safe_float(first.get(key))
    last_value = safe_float(last.get(key))
    if first_value is None or last_value is None:
        return None
    if last_value < first_value:
        return round(last_value, 6)
    return round(last_value - first_value, 6)


def counter_delta_map(first: dict[str, Any], last: dict[str, Any], key: str) -> dict[str, float]:
    first_map = first.get(key) if isinstance(first.get(key), dict) else {}
    last_map = last.get(key) if isinstance(last.get(key), dict) else {}
    out: dict[str, float] = {}
    for item_key in sorted(set(first_map) | set(last_map)):
        old = safe_float(first_map.get(item_key)) or 0.0
        new = safe_float(last_map.get(item_key)) or 0.0
        delta = new if new < old else new - old
        if delta:
            out[item_key] = round(delta, 6)
    return out


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"status": "empty", "sample_count": 0, "generated_at": now_iso()}
    first = samples[0]
    last = samples[-1]
    elapsed = max(0.0, float(last.get("sampled_epoch") or 0) - float(first.get("sampled_epoch") or 0))
    first_metrics = first.get("metrics") if isinstance(first.get("metrics"), dict) else {}
    last_metrics = last.get("metrics") if isinstance(last.get("metrics"), dict) else {}
    accepted_delta = counter_delta(first_metrics, last_metrics, "submit_accepted_total")
    rejected_delta = counter_delta(first_metrics, last_metrics, "submit_rejected_total")
    broadcast_delta = counter_delta(first_metrics, last_metrics, "template_broadcasts_total")
    job_age_p95_values = []
    ready_values = []
    submit_ready_values = []
    p2p_fresh_values = []
    for sample in samples:
        db = sample.get("db_submission_timing") if isinstance(sample.get("db_submission_timing"), dict) else {}
        age = db.get("job_age_ms") if isinstance(db.get("job_age_ms"), dict) else {}
        p95 = safe_float(age.get("p95"))
        if p95 is not None:
            job_age_p95_values.append(p95)
        metrics = sample.get("metrics") if isinstance(sample.get("metrics"), dict) else {}
        for values, key in (
            (ready_values, "ready_miners"),
            (submit_ready_values, "backend_submit_ready"),
            (p2p_fresh_values, "backend_p2p_fresh"),
        ):
            value = safe_float(metrics.get(key))
            if value is not None:
                values.append(value)
    return {
        "status": "ok",
        "generated_at": now_iso(),
        "sample_count": len(samples),
        "first_sample_at": first.get("sampled_at"),
        "last_sample_at": last.get("sampled_at"),
        "elapsed_seconds": elapsed,
        "accepted_submit_delta": accepted_delta,
        "rejected_submit_delta": rejected_delta,
        "rejected_per_accepted": round(rejected_delta / accepted_delta, 6)
        if accepted_delta and rejected_delta is not None
        else None,
        "submit_rejected_by_reason_delta": counter_delta_map(
            first_metrics,
            last_metrics,
            "submit_rejected_by_reason",
        ),
        "template_broadcast_delta": broadcast_delta,
        "template_invalidations_by_cause_delta": counter_delta_map(
            first_metrics,
            last_metrics,
            "template_invalidations_by_cause",
        ),
        "ready_miners_min": min(ready_values) if ready_values else None,
        "backend_submit_ready_min": min(submit_ready_values) if submit_ready_values else None,
        "backend_p2p_fresh_min": min(p2p_fresh_values) if p2p_fresh_values else None,
        "db_job_age_p95_ms_max": max(job_age_p95_values) if job_age_p95_values else None,
        "accepted_submit_per_hour": round(accepted_delta * 3600.0 / elapsed, 3)
        if accepted_delta is not None and elapsed > 0
        else None,
        "latest_global_paid": last.get("global_paid"),
        "latest_db_submission_timing": last.get("db_submission_timing"),
    }


def write_summary(session_dir: Path, samples: list[dict[str, Any]]) -> None:
    (session_dir / "summary.json").write_text(
        json.dumps(summarize_samples(samples), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def collect_sample(args: argparse.Namespace) -> dict[str, Any]:
    status, status_latency, status_error = fetch_json(args.status_url, args.timeout_seconds)
    global_paid, global_latency, global_error = fetch_json(args.global_paid_url, args.timeout_seconds)
    job_state, job_latency, job_error = fetch_json(args.job_state_url, args.timeout_seconds)
    asic, asic_latency, asic_error = fetch_json(args.asic_performance_url, args.timeout_seconds)
    metrics_text, metrics_latency, metrics_error = fetch_text(args.pool_metrics_url, args.timeout_seconds)
    return {
        "sampled_at": now_iso(),
        "sampled_epoch": seconds_since_epoch(),
        "status": compact_status(status, status_latency, status_error),
        "global_paid": compact_global_paid(global_paid, global_latency, global_error),
        "job_state": compact_job_state(job_state, job_latency, job_error),
        "asic_performance": compact_asic_performance(asic, asic_latency, asic_error),
        "metrics": compact_metrics(metrics_text, metrics_latency, metrics_error),
        "db_submission_timing": collect_db_submission_timing(args.db_window_seconds, args.timeout_seconds),
        "logs": {
            "node": collect_log_counts("node", args.log_lookback_seconds, NODE_LOG_PATTERNS, args.timeout_seconds),
            "pool": collect_log_counts("pool", args.log_lookback_seconds, POOL_LOG_PATTERNS, args.timeout_seconds),
        },
        "docker_stats": collect_docker_stats(args.timeout_seconds),
    }


def safe_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label.strip())
    return cleaned or "pipeline-profile"


def run_profiler(args: argparse.Namespace) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    session_dir = Path(args.output_dir).expanduser() / f"{safe_label(args.label)}-{stamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = session_dir / "samples.jsonl"
    latest_path = Path(args.output_dir).expanduser() / "latest-pipeline-profiler.txt"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(str(session_dir) + "\n", encoding="utf-8")
    write_manifest(session_dir, args)

    samples: list[dict[str, Any]] = []
    deadline = time.monotonic() + max(0.0, args.duration_seconds)
    while True:
        sample = collect_sample(args)
        samples.append(sample)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
        write_summary(session_dir, samples)
        if args.print_samples:
            print(json.dumps(sample, sort_keys=True), flush=True)
        if args.duration_seconds <= 0 or time.monotonic() >= deadline:
            break
        sleep_for = min(max(1.0, args.interval_seconds), max(0.0, deadline - time.monotonic()))
        if sleep_for > 0:
            time.sleep(sleep_for)
    return {
        "session_dir": str(session_dir),
        "jsonl_path": str(jsonl_path),
        "summary_path": str(session_dir / "summary.json"),
        "manifest_path": str(session_dir / "manifest.json"),
        "latest_path": str(latest_path),
        "summary": summarize_samples(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=5 * 60 * 60)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--db-window-seconds", type=int, default=300)
    parser.add_argument("--log-lookback-seconds", type=int, default=60)
    parser.add_argument("--status-url", default=DEFAULT_STATUS_URL)
    parser.add_argument("--global-paid-url", default=DEFAULT_GLOBAL_PAID_URL)
    parser.add_argument("--pool-metrics-url", default=DEFAULT_POOL_METRICS_URL)
    parser.add_argument("--job-state-url", default=DEFAULT_JOB_STATE_URL)
    parser.add_argument("--asic-performance-url", default=DEFAULT_ASIC_PERFORMANCE_URL)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--label", default="pipeline-profile")
    parser.add_argument("--print-samples", action="store_true")
    parser.add_argument("--json", action="store_true", help="print final JSON summary")
    args = parser.parse_args()
    result = run_profiler(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["session_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
