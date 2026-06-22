#!/usr/bin/env python3
"""Collect low-overhead optimization baseline samples for the BlockDAG stack."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from pool_ops import RUNTIME_DIR, collect_status_cached, host_runtime_profile, now_iso, seconds_since_epoch

DEFAULT_POOL_METRICS_URL = "http://127.0.0.1:9090/metrics"
DEFAULT_LOCAL_STATUS_MAX_AGE_SECONDS = 5.0
METRIC_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)$")
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return round(ordered[index], 3)


def number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_status_url(url: str, timeout: float) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}, round((time.monotonic() - started) * 1000, 3)


def fetch_text_url(url: str, timeout: float) -> tuple[str, float]:
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace"), round((time.monotonic() - started) * 1000, 3)


def parse_prometheus_metrics(text: str) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = METRIC_RE.match(line)
        if not match:
            continue
        name, raw_labels, raw_value = match.groups()
        labels = tuple(sorted((item.group(1), bytes(item.group(2), "utf-8").decode("unicode_escape")) for item in LABEL_RE.finditer(raw_labels or "")))
        metrics[(name, labels)] = float(raw_value)
    return metrics


def metric_labels_match(labels: tuple[tuple[str, str], ...], wanted: dict[str, str]) -> bool:
    found = dict(labels)
    return all(found.get(key) == value for key, value in wanted.items())


def metric_sum(metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float], name: str, labels: dict[str, str] | None = None) -> float | None:
    values = [
        value
        for (metric_name, metric_labels), value in metrics.items()
        if metric_name == name and (not labels or metric_labels_match(metric_labels, labels))
    ]
    if not values:
        return None
    return round(sum(values), 6)


def metric_sum_by_label(
    metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    name: str,
    group_label: str,
    labels: dict[str, str] | None = None,
    exclude_labels: dict[str, str] | None = None,
) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for (metric_name, metric_labels), value in metrics.items():
        if metric_name != name:
            continue
        label_map = dict(metric_labels)
        if labels and not all(label_map.get(key) == wanted for key, wanted in labels.items()):
            continue
        if exclude_labels and any(label_map.get(key) == unwanted for key, unwanted in exclude_labels.items()):
            continue
        key = label_map.get(group_label) or "unlabeled"
        grouped[key] = round(grouped.get(key, 0.0) + value, 6)
    return dict(sorted(grouped.items()))


def metric_max(metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float], name: str) -> float | None:
    values = [value for (metric_name, _), value in metrics.items() if metric_name == name]
    if not values:
        return None
    return round(max(values), 6)


def flatten_pool_metrics(metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float], latency_ms: float | None = None, error: str | None = None) -> dict[str, Any]:
    block_rejected = 0.0
    block_rejected_seen = False
    for (name, labels), value in metrics.items():
        if name != "pool_block_submit_outcomes_total":
            continue
        label_map = dict(labels)
        if label_map.get("outcome") != "accepted":
            block_rejected += value
            block_rejected_seen = True

    return {
        "pool_metrics_latency_ms": latency_ms,
        "pool_metrics_error": error,
        "pool_active_connections": metric_sum(metrics, "pool_active_connections"),
        "pool_job_health_ok": metric_max(metrics, "pool_job_health_ok"),
        "pool_job_health_authorized_miners": metric_sum(metrics, "pool_job_health_authorized_miners"),
        "pool_job_health_ready_miners": metric_sum(metrics, "pool_job_health_ready_miners"),
        "pool_blocks_found_total": metric_sum(metrics, "pool_blocks_found_total"),
        "pool_block_submit_accepted_total": metric_sum(metrics, "pool_block_submit_outcomes_total", {"outcome": "accepted"}),
        "pool_block_submit_rejected_total": round(block_rejected, 6) if block_rejected_seen else None,
        "pool_block_submit_rejected_by_reason": metric_sum_by_label(
            metrics,
            "pool_block_submit_outcomes_total",
            "reason",
            exclude_labels={"outcome": "accepted"},
        ),
        "pool_shares_accepted_total": metric_sum(metrics, "pool_shares_accepted_total"),
        "pool_shares_rejected_total": metric_sum(metrics, "pool_shares_rejected_total"),
        "pool_share_reject_by_reason": metric_sum_by_label(metrics, "pool_shares_rejected_total", "reason"),
        "pool_backend_mineable": metric_max(metrics, "pool_rpc_backend_node_health_mineable"),
        "pool_backend_submit_ready": metric_max(metrics, "pool_rpc_backend_node_health_submit_ready"),
        "pool_backend_p2p_mining_fresh": metric_max(metrics, "pool_rpc_backend_node_health_p2p_mining_fresh"),
        "pool_backend_p2p_consensus_peer_count": metric_max(metrics, "pool_rpc_backend_node_health_p2p_consensus_peer_count"),
        "pool_backend_p2p_fresh_consensus_peer_count": metric_max(metrics, "pool_rpc_backend_node_health_p2p_fresh_consensus_peer_count"),
        "pool_backend_p2p_best_peer_lead_blocks": metric_max(metrics, "pool_rpc_backend_node_health_p2p_best_peer_lead_blocks"),
        "pool_backend_p2p_best_peer_graph_state_age_seconds": metric_max(metrics, "pool_rpc_backend_node_health_p2p_best_peer_graph_state_age_seconds"),
        "pool_template_conversion_failure_ratio": metric_max(metrics, "pool_template_conversion_stall_failure_ratio"),
        "pool_template_conversion_window_total": metric_sum(metrics, "pool_template_conversion_stall_window_candidates", {"kind": "total"}),
        "pool_template_conversion_window_failed": metric_sum(metrics, "pool_template_conversion_stall_window_candidates", {"kind": "failed"}),
        "pool_template_conversion_window_accepted": metric_sum(metrics, "pool_template_conversion_stall_window_candidates", {"kind": "accepted"}),
        "pool_template_invalidation_by_cause": metric_sum_by_label(
            metrics,
            "pool_rpc_backend_node_health_template_invalidations_total",
            "cause",
        ),
        "pool_clean_refresh_by_event": metric_sum_by_label(metrics, "pool_clean_template_refresh_events_total", "event"),
    }


def collect_pool_metrics_sample(metrics_url: str | None, timeout: float) -> dict[str, Any]:
    if not metrics_url:
        return {}
    try:
        text, latency_ms = fetch_text_url(metrics_url, min(timeout, 3.0))
        return flatten_pool_metrics(parse_prometheus_metrics(text), latency_ms=latency_ms)
    except Exception as exc:  # noqa: BLE001 - measurement must not fail when metrics are absent.
        return flatten_pool_metrics({}, error=str(exc))


def collect_status_sample(
    status_url: str | None = None,
    timeout: float = 8.0,
    pool_metrics_url: str | None = DEFAULT_POOL_METRICS_URL,
    local_status_max_age_seconds: float = DEFAULT_LOCAL_STATUS_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    started = time.monotonic()
    dashboard_latency_ms = None
    if status_url:
        status, dashboard_latency_ms = fetch_status_url(status_url, timeout)
        source = status_url
    else:
        status = collect_status_cached(include_logs=False, max_age_seconds=local_status_max_age_seconds)
        source = "local-collector"
    collection_ms = round((time.monotonic() - started) * 1000, 3)
    sample = flatten_status_sample(status, source, collection_ms, dashboard_latency_ms)
    sample.update(collect_pool_metrics_sample(pool_metrics_url, timeout))
    return sample


def sync_current_block_source(sync: dict[str, Any], nodes: dict[str, Any], current_block: float | None) -> str | None:
    source = sync.get("current_block_source")
    if source:
        return str(source)
    chain_block_count = number(sync.get("chain_block_count"))
    if current_block is not None and chain_block_count is not None and int(current_block) == int(chain_block_count):
        return str(sync.get("source") or "native-chain-block-count")
    node_sources: set[str] = set()
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        node_current = number(node.get("current_block"))
        node_source = node.get("current_block_source") or node.get("chain_rpc_source")
        if current_block is not None and node_current is not None and int(current_block) == int(node_current) and node_source:
            node_sources.add(str(node_source))
    if len(node_sources) == 1:
        return next(iter(node_sources))
    return None


def flatten_status_sample(
    status: dict[str, Any],
    source: str,
    collection_ms: float,
    dashboard_latency_ms: float | None = None,
) -> dict[str, Any]:
    sync = status.get("sync_progress") if isinstance(status.get("sync_progress"), dict) else {}
    host = status.get("host_pressure") if isinstance(status.get("host_pressure"), dict) else {}
    adaptive = status.get("adaptive_concurrency") if isinstance(status.get("adaptive_concurrency"), dict) else {}
    miner = status.get("miner_health") if isinstance(status.get("miner_health"), dict) else {}
    sampler = status.get("status_sampler") if isinstance(status.get("status_sampler"), dict) else {}
    nodes = sync.get("nodes") if isinstance(sync.get("nodes"), dict) else {}
    chain_latencies = [
        value
        for value in (number(item.get("chain_rpc_latency_ms")) for item in nodes.values() if isinstance(item, dict))
        if value is not None
    ]
    current_block = number(sync.get("current_block"))
    highest_block = number(sync.get("highest_block"))
    p2p_connections = number(sync.get("p2p_connections"))
    p2p_network_gap = number(sync.get("p2p_network_gap"))
    current_block_source = sync_current_block_source(sync, nodes, current_block)
    adaptive_workers = adaptive.get("workers") if isinstance(adaptive.get("workers"), dict) else {}
    return {
        "sampled_at": now_iso(),
        "sampled_epoch": seconds_since_epoch(),
        "source": source,
        "collection_ms": collection_ms,
        "dashboard_latency_ms": dashboard_latency_ms,
        "status_age_seconds": number(status.get("age_seconds")),
        "status_fresh": status.get("fresh"),
        "status_sampler_hit": sampler.get("hit"),
        "status_sampler_age_seconds": number(sampler.get("age_seconds")),
        "overall": status.get("overall"),
        "mode": status.get("mode"),
        "can_mine": status.get("can_mine"),
        "can_accept_shares": status.get("can_accept_shares"),
        "can_submit_blocks": status.get("can_submit_blocks"),
        "sync_status": sync.get("status"),
        "current_block": int(current_block) if current_block is not None else None,
        "highest_block": int(highest_block) if highest_block is not None else None,
        "current_block_source": current_block_source,
        "remaining_blocks": int(number(sync.get("remaining_blocks")) or 0) if sync.get("remaining_blocks") is not None else None,
        "native_is_current": sync.get("native_is_current"),
        "chain_syncing": sync.get("chain_syncing"),
        "mining_advisory_sync": sync.get("mining_advisory_sync"),
        "p2p_connections": int(p2p_connections) if p2p_connections is not None else None,
        "p2p_network_gap": int(p2p_network_gap) if p2p_network_gap is not None else None,
        "chain_rpc_latency_ms_max": max(chain_latencies) if chain_latencies else None,
        "chain_rpc_latency_ms_avg": round(sum(chain_latencies) / len(chain_latencies), 3) if chain_latencies else None,
        "connected_miners": int(number(miner.get("connected_count")) or 0),
        "managed_miners": int(number(miner.get("managed_count")) or 0),
        "iowait_percent": number(host.get("iowait_percent")),
        "cpu_busy_percent": number(host.get("cpu_busy_percent")),
        "io_some_avg10": number(host.get("io_some_avg10")),
        "cpu_some_avg10": number(host.get("cpu_some_avg10")),
        "memory_some_avg10": number(host.get("memory_some_avg10")),
        "adaptive_pressure_level": adaptive.get("pressure_level"),
        "adaptive_workers": adaptive_workers,
        "host_profile": status.get("host_profile") or adaptive.get("host_profile") or host_runtime_profile(),
    }


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "sample_count": 0,
            "status": "empty",
            "generated_at": now_iso(),
            "host_profile": host_runtime_profile(),
        }
    first = samples[0]
    last = samples[-1]
    elapsed = max(0, float(last.get("sampled_epoch") or 0) - float(first.get("sampled_epoch") or 0))
    first_block = number(first.get("current_block"))
    last_block = number(last.get("current_block"))
    first_block_source = str(first.get("current_block_source") or "")
    last_block_source = str(last.get("current_block_source") or "")
    block_source_missing = not first_block_source or not last_block_source
    block_source_changed = bool(first_block_source and last_block_source and first_block_source != last_block_source)
    block_delta = None
    blocks_per_second = None
    block_delta_valid = False
    if first_block is not None and last_block is not None:
        raw_block_delta = int(last_block - first_block)
        block_delta_valid = bool(raw_block_delta >= 0 and not block_source_missing and not block_source_changed)
        if block_delta_valid:
            block_delta = raw_block_delta
        if elapsed > 0 and block_delta is not None:
            blocks_per_second = round(block_delta / elapsed, 4)

    def values(field: str) -> list[float]:
        return [value for value in (number(sample.get(field)) for sample in samples) if value is not None]

    def counter_delta(field: str, *, missing_initial_zero: bool = False) -> float | None:
        first_value = number(first.get(field))
        last_value = number(last.get(field))
        if first_value is None and missing_initial_zero and last_value is not None and not first.get("pool_metrics_error"):
            first_value = 0.0
        if first_value is None or last_value is None:
            return None
        if last_value < first_value:
            return round(last_value, 6)
        return round(last_value - first_value, 6)

    def counter_delta_map(field: str) -> dict[str, float]:
        first_values = first.get(field) if isinstance(first.get(field), dict) else {}
        last_values = last.get(field) if isinstance(last.get(field), dict) else {}
        deltas: dict[str, float] = {}
        for key in sorted(set(first_values) | set(last_values)):
            first_value = number(first_values.get(key)) or 0.0
            last_value = number(last_values.get(key)) or 0.0
            delta = last_value if last_value < first_value else last_value - first_value
            if delta != 0:
                deltas[str(key)] = round(delta, 6)
        return deltas

    def bool_values(field: str) -> list[str]:
        found: set[str] = set()
        for sample in samples:
            value = sample.get(field)
            if isinstance(value, bool):
                found.add("true" if value else "false")
            elif value is not None:
                found.add(str(value))
        return sorted(found)

    accepted_delta = counter_delta("pool_block_submit_accepted_total")
    rejected_delta = counter_delta("pool_block_submit_rejected_total", missing_initial_zero=True)
    shares_accepted_delta = counter_delta("pool_shares_accepted_total")
    shares_rejected_delta = counter_delta("pool_shares_rejected_total", missing_initial_zero=True)

    worker_ranges: dict[str, dict[str, int]] = {}
    for sample in samples:
        workers = sample.get("adaptive_workers") if isinstance(sample.get("adaptive_workers"), dict) else {}
        for key, raw in workers.items():
            value = int(number(raw) or 0)
            if value <= 0:
                continue
            row = worker_ranges.setdefault(key, {"min": value, "max": value})
            row["min"] = min(row["min"], value)
            row["max"] = max(row["max"], value)

    return {
        "status": "ok",
        "generated_at": now_iso(),
        "sample_count": len(samples),
        "first_sample_at": first.get("sampled_at"),
        "last_sample_at": last.get("sampled_at"),
        "elapsed_seconds": elapsed,
        "source": last.get("source"),
        "host_profile": last.get("host_profile") or host_runtime_profile(),
        "overall_values": sorted({str(sample.get("overall")) for sample in samples if sample.get("overall")}),
        "mode_values": sorted({str(sample.get("mode")) for sample in samples if sample.get("mode")}),
        "sync_status_values": sorted({str(sample.get("sync_status")) for sample in samples if sample.get("sync_status")}),
        "block_delta": block_delta,
        "block_delta_valid": block_delta_valid,
        "block_delta_warning": "current_block source missing, changed, or moved backwards"
        if not block_delta_valid and first_block is not None and last_block is not None
        else "",
        "blocks_per_second": blocks_per_second,
        "current_block_first": first.get("current_block"),
        "current_block_last": last.get("current_block"),
        "current_block_source_first": first.get("current_block_source"),
        "current_block_source_last": last.get("current_block_source"),
        "remaining_blocks_last": last.get("remaining_blocks"),
        "can_mine_values": bool_values("can_mine"),
        "can_submit_blocks_values": bool_values("can_submit_blocks"),
        "native_is_current_values": bool_values("native_is_current"),
        "chain_syncing_values": bool_values("chain_syncing"),
        "mining_advisory_sync_values": bool_values("mining_advisory_sync"),
        "p2p_connections_min": min(values("p2p_connections") or [0]),
        "p2p_network_gap_max": percentile(values("p2p_network_gap"), 100),
        "connected_miners_max": max(values("connected_miners") or [0]),
        "managed_miners_max": max(values("managed_miners") or [0]),
        "pool_active_connections_max": max(values("pool_active_connections") or [0]),
        "pool_ready_miners_min": min(values("pool_job_health_ready_miners") or [0]),
        "pool_ready_miners_max": max(values("pool_job_health_ready_miners") or [0]),
        "pool_backend_mineable_min": min(values("pool_backend_mineable") or [0]),
        "pool_backend_submit_ready_min": min(values("pool_backend_submit_ready") or [0]),
        "pool_backend_p2p_fresh_min": min(values("pool_backend_p2p_mining_fresh") or [0]),
        "pool_backend_peer_lead_max": percentile(values("pool_backend_p2p_best_peer_lead_blocks"), 100),
        "pool_fresh_consensus_peers_min": min(values("pool_backend_p2p_fresh_consensus_peer_count") or [0]),
        "pool_block_submit_accepted_delta": accepted_delta,
        "pool_block_submit_rejected_delta": rejected_delta,
        "pool_block_submit_rejected_per_accepted": round(rejected_delta / accepted_delta, 6) if accepted_delta and rejected_delta is not None else None,
        "pool_block_submit_rejected_by_reason_delta": counter_delta_map("pool_block_submit_rejected_by_reason"),
        "pool_accepted_blocks_per_hour": round(accepted_delta * 3600.0 / elapsed, 3) if accepted_delta is not None and elapsed > 0 else None,
        "pool_blocks_found_delta": counter_delta("pool_blocks_found_total"),
        "pool_shares_accepted_delta": shares_accepted_delta,
        "pool_shares_rejected_delta": shares_rejected_delta,
        "pool_share_reject_ratio": round(shares_rejected_delta / max(1.0, shares_accepted_delta + shares_rejected_delta), 6)
        if shares_accepted_delta is not None and shares_rejected_delta is not None
        else None,
        "pool_share_reject_by_reason_delta": counter_delta_map("pool_share_reject_by_reason"),
        "pool_template_invalidation_by_cause_delta": counter_delta_map("pool_template_invalidation_by_cause"),
        "pool_clean_refresh_by_event_delta": counter_delta_map("pool_clean_refresh_by_event"),
        "pool_template_conversion_failure_ratio_max": percentile(values("pool_template_conversion_failure_ratio"), 100),
        "collection_ms_p95": percentile(values("collection_ms"), 95),
        "dashboard_latency_ms_p95": percentile(values("dashboard_latency_ms"), 95),
        "status_age_seconds_p95": percentile(values("status_age_seconds"), 95),
        "status_age_seconds_max": percentile(values("status_age_seconds"), 100),
        "status_sampler_hit_values": bool_values("status_sampler_hit"),
        "pool_metrics_latency_ms_p95": percentile(values("pool_metrics_latency_ms"), 95),
        "chain_rpc_latency_ms_p95": percentile(values("chain_rpc_latency_ms_max"), 95),
        "iowait_percent_max": percentile(values("iowait_percent"), 100),
        "io_some_avg10_max": percentile(values("io_some_avg10"), 100),
        "cpu_some_avg10_max": percentile(values("cpu_some_avg10"), 100),
        "adaptive_worker_ranges": worker_ranges,
    }


def html_escape(value: Any) -> str:
    text = str(value if value is not None else "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html_report(summary: dict[str, Any], samples: list[dict[str, Any]]) -> str:
    rows = [
        ("Samples", summary.get("sample_count")),
        ("Elapsed seconds", summary.get("elapsed_seconds")),
        ("Source", summary.get("source")),
        ("Modes", ", ".join(summary.get("mode_values") or [])),
        ("Sync statuses", ", ".join(summary.get("sync_status_values") or [])),
        ("Can submit values", ", ".join(summary.get("can_submit_blocks_values") or [])),
        ("Native current values", ", ".join(summary.get("native_is_current_values") or [])),
        ("Mining advisory sync values", ", ".join(summary.get("mining_advisory_sync_values") or [])),
        ("Block delta", summary.get("block_delta")),
        ("Block delta valid", summary.get("block_delta_valid")),
        ("Block delta warning", summary.get("block_delta_warning")),
        ("Current block source first/last", f"{summary.get('current_block_source_first')} / {summary.get('current_block_source_last')}"),
        ("Blocks/sec", summary.get("blocks_per_second")),
        ("Pool accepted blocks delta", summary.get("pool_block_submit_accepted_delta")),
        ("Pool rejected blocks delta", summary.get("pool_block_submit_rejected_delta")),
        ("Pool rejected / accepted", summary.get("pool_block_submit_rejected_per_accepted")),
        ("Pool rejected reasons", json.dumps(summary.get("pool_block_submit_rejected_by_reason_delta") or {}, sort_keys=True)),
        ("Pool accepted blocks / hour", summary.get("pool_accepted_blocks_per_hour")),
        ("Pool found blocks delta", summary.get("pool_blocks_found_delta")),
        ("Pool accepted shares delta", summary.get("pool_shares_accepted_delta")),
        ("Pool rejected shares delta", summary.get("pool_shares_rejected_delta")),
        ("Pool share reject ratio", summary.get("pool_share_reject_ratio")),
        ("Pool share reject reasons", json.dumps(summary.get("pool_share_reject_by_reason_delta") or {}, sort_keys=True)),
        ("Pool active connections max", summary.get("pool_active_connections_max")),
        ("Pool ready miners min/max", f"{summary.get('pool_ready_miners_min')} / {summary.get('pool_ready_miners_max')}"),
        ("Pool backend mineable min", summary.get("pool_backend_mineable_min")),
        ("Pool backend submit-ready min", summary.get("pool_backend_submit_ready_min")),
        ("Pool P2P fresh min", summary.get("pool_backend_p2p_fresh_min")),
        ("Pool backend peer lead max", summary.get("pool_backend_peer_lead_max")),
        ("P2P connections min", summary.get("p2p_connections_min")),
        ("P2P network gap max", summary.get("p2p_network_gap_max")),
        ("Pool fresh consensus peers min", summary.get("pool_fresh_consensus_peers_min")),
        ("Template invalidation causes", json.dumps(summary.get("pool_template_invalidation_by_cause_delta") or {}, sort_keys=True)),
        ("Clean refresh events", json.dumps(summary.get("pool_clean_refresh_by_event_delta") or {}, sort_keys=True)),
        ("Pool conversion failure max %", summary.get("pool_template_conversion_failure_ratio_max")),
        ("Collection p95 ms", summary.get("collection_ms_p95")),
        ("Dashboard p95 ms", summary.get("dashboard_latency_ms_p95")),
        ("Status age p95 / max s", f"{summary.get('status_age_seconds_p95')} / {summary.get('status_age_seconds_max')}"),
        ("Status sampler hit values", ", ".join(summary.get("status_sampler_hit_values") or [])),
        ("Pool metrics p95 ms", summary.get("pool_metrics_latency_ms_p95")),
        ("Chain RPC p95 ms", summary.get("chain_rpc_latency_ms_p95")),
        ("I/O wait max %", summary.get("iowait_percent_max")),
        ("IO PSI avg10 max", summary.get("io_some_avg10_max")),
        ("CPU PSI avg10 max", summary.get("cpu_some_avg10_max")),
    ]
    metric_rows = "\n".join(
        f"<tr><th>{html_escape(label)}</th><td>{html_escape(value)}</td></tr>"
        for label, value in rows
    )
    worker_rows = "\n".join(
        f"<tr><td>{html_escape(kind)}</td><td>{limits['min']}</td><td>{limits['max']}</td></tr>"
        for kind, limits in sorted((summary.get("adaptive_worker_ranges") or {}).items())
    )
    last_samples = samples[-12:]
    sample_rows = "\n".join(
        "<tr>"
        f"<td>{html_escape(sample.get('sampled_at'))}</td>"
        f"<td>{html_escape(sample.get('overall'))}</td>"
        f"<td>{html_escape(sample.get('mode'))}</td>"
        f"<td>{html_escape(sample.get('sync_status'))}</td>"
        f"<td>{html_escape(sample.get('can_submit_blocks'))}</td>"
        f"<td>{html_escape(sample.get('native_is_current'))}</td>"
        f"<td>{html_escape(sample.get('mining_advisory_sync'))}</td>"
        f"<td>{html_escape(sample.get('status_age_seconds'))}</td>"
        f"<td>{html_escape(sample.get('current_block'))}</td>"
        f"<td>{html_escape(sample.get('current_block_source'))}</td>"
        f"<td>{html_escape(sample.get('remaining_blocks'))}</td>"
        f"<td>{html_escape(sample.get('chain_rpc_latency_ms_max'))}</td>"
        f"<td>{html_escape(sample.get('iowait_percent'))}</td>"
        f"<td>{html_escape(sample.get('pool_block_submit_accepted_total'))}</td>"
        f"<td>{html_escape(sample.get('pool_job_health_ready_miners'))}</td>"
        f"<td>{html_escape(sample.get('pool_backend_submit_ready'))}</td>"
        f"<td>{html_escape(sample.get('pool_backend_p2p_mining_fresh'))}</td>"
        "</tr>"
        for sample in last_samples
    )
    host_profile = summary.get("host_profile") if isinstance(summary.get("host_profile"), dict) else {}
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BlockDAG Optimization Measurement</title>
  <style>body{{font:14px/1.5 system-ui,sans-serif;max-width:1120px;margin:32px auto;padding:0 20px;background:#0d1117;color:#eef3f8}}table{{width:100%;border-collapse:collapse;margin:16px 0}}td,th{{border:1px solid #303b4d;padding:8px;text-align:left}}th{{background:#1d2633}}code{{background:#090d13;border:1px solid #303b4d;border-radius:5px;padding:1px 5px}}</style>
</head>
<body>
  <h1>BlockDAG Optimization Measurement</h1>
  <p>Generated: <code>{html_escape(summary.get('generated_at'))}</code></p>
  <p>Host profile: <code>{html_escape(host_profile.get('profile'))}</code>, OS <code>{html_escape(host_profile.get('os'))}</code>, arch <code>{html_escape(host_profile.get('arch'))}</code>, CPU <code>{html_escape(host_profile.get('cpu_count'))}</code>, memory GiB <code>{html_escape(host_profile.get('memory_gib'))}</code></p>
  <h2>Summary</h2>
  <table>{metric_rows}</table>
  <h2>Adaptive Worker Ranges</h2>
  <table><tr><th>Kind</th><th>Min</th><th>Max</th></tr>{worker_rows}</table>
  <h2>Recent Samples</h2>
  <table><tr><th>Time</th><th>Overall</th><th>Mode</th><th>Sync</th><th>Can Submit</th><th>Native Current</th><th>Advisory Sync</th><th>Status Age s</th><th>Block</th><th>Block Source</th><th>Remaining</th><th>RPC ms</th><th>IO wait %</th><th>Accepted Blocks</th><th>Ready Miners</th><th>Submit Ready</th><th>P2P Fresh</th></tr>{sample_rows}</table>
</body>
</html>
"""


def run_measurement(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in args.label.strip()) or "measurement"
    jsonl_path = output_dir / f"{label}-{stamp}.jsonl"
    samples: list[dict[str, Any]] = []
    deadline = time.monotonic() + max(0.0, args.duration_seconds)
    while True:
        sample = collect_status_sample(
            args.status_url,
            timeout=args.timeout_seconds,
            pool_metrics_url=args.pool_metrics_url,
            local_status_max_age_seconds=args.local_status_max_age_seconds,
        )
        samples.append(sample)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
        if time.monotonic() >= deadline or args.duration_seconds <= 0:
            break
        sleep_for = min(max(0.1, args.interval_seconds), max(0.0, deadline - time.monotonic()))
        if sleep_for > 0:
            time.sleep(sleep_for)

    summary = summarize_samples(samples)
    summary["label"] = label
    summary["jsonl_path"] = str(jsonl_path)
    summary_path = output_dir / f"{label}-{stamp}.summary.json"
    html_path = output_dir / f"{label}-{stamp}.html"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html_report(summary, samples), encoding="utf-8")
    latest_path = output_dir / "latest-optimization-measurement.txt"
    latest_path.write_text(str(html_path) + "\n", encoding="utf-8")
    return {**summary, "summary_path": str(summary_path), "html_path": str(html_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=60.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--status-url", help="optional dashboard /api/status URL to measure HTTP latency")
    parser.add_argument(
        "--local-status-max-age-seconds",
        type=float,
        default=DEFAULT_LOCAL_STATUS_MAX_AGE_SECONDS,
        help="maximum cached local status age when --status-url is not used",
    )
    parser.add_argument("--pool-metrics-url", default=DEFAULT_POOL_METRICS_URL, help="optional pool Prometheus /metrics URL")
    parser.add_argument("--no-pool-metrics", action="store_true", help="skip pool Prometheus metrics collection")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--output-dir", default=str(RUNTIME_DIR / "measurements"))
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()
    if args.no_pool_metrics:
        args.pool_metrics_url = None
    result = run_measurement(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["html_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
