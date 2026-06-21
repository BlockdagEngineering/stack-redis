#!/usr/bin/env python3

import os
import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

OPS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS_DIR))

import pool_ops  # noqa: E402
import status_sampler  # noqa: E402


class StatusSamplerMiningImperativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.originals = {
            name: getattr(status_sampler, name)
            for name in (
                "MINING_IMPERATIVE_REPAIR_ENABLED",
                "MINING_IMPERATIVE_GUARD_UNITS",
                "MINING_IMPERATIVE_START_POOL_ENABLED",
                "MINING_IMPERATIVE_START_IDLE_SYNCED_POOL",
                "MINING_IMPERATIVE_MINER_TRACKING_REPAIR_ENABLED",
                "MINING_IMPERATIVE_MINER_ACTIVITY_REPAIR_ENABLED",
                "MINING_IMPERATIVE_MINER_ACTIVITY_STALE_SECONDS",
                "MINING_IMPERATIVE_NODE_MINING_REPAIR_ENABLED",
                "MINING_IMPERATIVE_FASTSYNC_PEER_QUARANTINE_ENABLED",
                "MINING_IMPERATIVE_CHAIN_STATE_RESTORE_ENABLED",
                "CATCHUP_PAUSE_ENABLED",
                "CATCHUP_PAUSE_ON_SYNCING",
                "CATCHUP_PAUSE_THRESHOLD_BLOCKS",
                "CATCHUP_NODE_RECREATE_ENABLED",
                "CATCHUP_NODE_CACHE_MB",
                "CATCHUP_NODE_CACHE_MIN_MB",
                "CATCHUP_NODE_CACHE_MEMORY_PERCENT",
                "CATCHUP_IO_PRESSURE_PAUSE_ENABLED",
                "CATCHUP_IO_PRESSURE_MIN_LAG_BLOCKS",
                "CATCHUP_IOWAIT_WARN_PERCENT",
                "CATCHUP_IO_SOME_AVG10_WARN",
                "CATCHUP_IO_FULL_AVG10_WARN",
                "CHAIN_STATE_STALLED_IMPORT_RESTORE_ENABLED",
                "CHAIN_STATE_STALLED_IMPORT_RESTORE_SECONDS",
                "CHAIN_STATE_STALLED_IMPORT_RESTORE_PEER_AHEAD_BLOCKS",
                "CHAIN_STATE_STALLED_IMPORT_RESTORE_GAP_GROWTH_BLOCKS",
                "CHAIN_STATE_IMPORT_WATCH_FILE",
                "EVM_REFERENCE_GAP_STALL_RESTORE_ENABLED",
                "EVM_REFERENCE_GAP_STALL_RESTORE_SECONDS",
                "EVM_REFERENCE_GAP_STALL_MIN_LAG_BLOCKS",
                "EVM_REFERENCE_GAP_STALL_MIN_IMPROVEMENT_BLOCKS",
                "EVM_REFERENCE_GAP_WATCH_FILE",
                "append_incident",
                "collect_pool_activity",
                "detect_total_memory_bytes",
                "log",
                "POOL_ENV_FILE",
                "PROJECT_ROOT",
                "read_neighbor_macs",
                "read_miner_registry",
                "run",
                "save_miner_registry",
                "set_runtime_env_value",
                "start_chain_state_self_heal",
                "update_stalled_import_watch",
                "upsert_pool_activity_miners",
            )
        }
        self.original_env = dict(os.environ)
        self.original_check_mutation_allowed = status_sampler.automation_control.check_mutation_allowed
        self.addCleanup(self.restore)
        status_sampler.automation_control.check_mutation_allowed = (
            lambda *_args, **_kwargs: SimpleNamespace(allowed=True, reason="unit test allow")
        )
        status_sampler.append_incident = lambda *args, **kwargs: {}
        status_sampler.config_value = lambda name, default="": os.environ.get(name, default)
        status_sampler.log = lambda _message: None
        status_sampler.MINING_IMPERATIVE_REPAIR_ENABLED = True
        status_sampler.MINING_IMPERATIVE_START_POOL_ENABLED = True
        status_sampler.MINING_IMPERATIVE_START_IDLE_SYNCED_POOL = False
        status_sampler.MINING_IMPERATIVE_MINER_TRACKING_REPAIR_ENABLED = True
        status_sampler.MINING_IMPERATIVE_MINER_ACTIVITY_REPAIR_ENABLED = True
        status_sampler.MINING_IMPERATIVE_MINER_ACTIVITY_STALE_SECONDS = 180
        status_sampler.MINING_IMPERATIVE_NODE_MINING_REPAIR_ENABLED = True
        status_sampler.MINING_IMPERATIVE_FASTSYNC_PEER_QUARANTINE_ENABLED = True
        status_sampler.MINING_IMPERATIVE_CHAIN_STATE_RESTORE_ENABLED = True
        status_sampler.POOL_ENV_FILE = pathlib.Path("/nonexistent/status-sampler-test.env")
        status_sampler.PROJECT_ROOT = pathlib.Path("/nonexistent/status-sampler-test-root")
        status_sampler.CATCHUP_PAUSE_ENABLED = True
        status_sampler.CATCHUP_PAUSE_ON_SYNCING = True
        status_sampler.CATCHUP_PAUSE_THRESHOLD_BLOCKS = 300
        status_sampler.CATCHUP_NODE_RECREATE_ENABLED = True
        status_sampler.CATCHUP_NODE_CACHE_MB = 6144
        status_sampler.CATCHUP_NODE_CACHE_MIN_MB = 1024
        status_sampler.CATCHUP_NODE_CACHE_MEMORY_PERCENT = 40.0
        status_sampler.CATCHUP_IO_PRESSURE_PAUSE_ENABLED = True
        status_sampler.CATCHUP_IO_PRESSURE_MIN_LAG_BLOCKS = 25
        status_sampler.CATCHUP_IOWAIT_WARN_PERCENT = 15.0
        status_sampler.CATCHUP_IO_SOME_AVG10_WARN = 20.0
        status_sampler.CATCHUP_IO_FULL_AVG10_WARN = 10.0
        status_sampler.CHAIN_STATE_STALLED_IMPORT_RESTORE_ENABLED = True
        status_sampler.CHAIN_STATE_STALLED_IMPORT_RESTORE_SECONDS = 900
        status_sampler.CHAIN_STATE_STALLED_IMPORT_RESTORE_PEER_AHEAD_BLOCKS = 1000
        status_sampler.CHAIN_STATE_STALLED_IMPORT_RESTORE_GAP_GROWTH_BLOCKS = 60
        status_sampler.EVM_REFERENCE_GAP_STALL_RESTORE_ENABLED = True
        status_sampler.EVM_REFERENCE_GAP_STALL_RESTORE_SECONDS = 900
        status_sampler.EVM_REFERENCE_GAP_STALL_MIN_LAG_BLOCKS = 1000
        status_sampler.EVM_REFERENCE_GAP_STALL_MIN_IMPROVEMENT_BLOCKS = 60
        os.environ["BDAG_ALLOW_UNSYNCED_NODE_MINING"] = "0"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        os.environ["MINING_ADDRESS"] = ""
        os.environ["MINING_POOL_ADDRESS"] = ""
        os.environ["NODE_ARGS_APPEND"] = ""
        os.environ["POOL_COINBASE_ADDRESS"] = ""
        for key in (
            "BDAG_COMPOSE_PROJECT_NAME",
            "COMPOSE_PROJECT_NAME",
        ):
            os.environ.pop(key, None)

    def restore(self) -> None:
        for name, value in self.originals.items():
            setattr(status_sampler, name, value)
        status_sampler.automation_control.check_mutation_allowed = self.original_check_mutation_allowed
        os.environ.clear()
        os.environ.update(self.original_env)

    def command_result(self, command: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
        return pool_ops.CommandResult(command, returncode, stdout, stderr, 0.0)

    def test_set_env_file_value_quotes_values_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = pathlib.Path(tmp) / ".env"
            env_path.write_text("NODE_ARGS_APPEND=\n", encoding="utf-8")

            changed = status_sampler.set_env_file_value(
                env_path,
                "NODE_ARGS_APPEND",
                "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc",
            )

            self.assertTrue(changed)
            self.assertIn(
                'NODE_ARGS_APPEND="--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"',
                env_path.read_text(encoding="utf-8"),
            )

    def pool_compose_start_seen(self, commands: list[list[str]]) -> bool:
        return any(
            "compose" in command
            and "up" in command
            and "--no-deps" in command
            and "--no-build" in command
            and "--pull" in command
            and "never" in command
            and command[-1] == status_sampler.POOL_CONTAINER
            for command in commands
        )

    def canonical_safety(self, safe: bool = True) -> dict:
        return {
            "safe": safe,
            "schema": "stack_evm_public_reference_v1",
            "reason": "external public-chain proof matches local node" if safe else "public-chain proof failed",
        }

    def native_template_health(self, safe: bool = True) -> dict:
        return {
            "chain_current": safe,
            "p2p_mining_fresh": safe,
            "p2p_mining_fresh_reason_code": "ok" if safe else "no_fresh_peers",
            "p2p_fresh_consensus_peer_count": 2 if safe else 0,
            "p2p_best_peer_lead_blocks": 0,
            "get_block_template_ready": safe,
            "submit_ready": safe,
            "mineable_now": safe,
            "template_usable": safe,
            "sync_allowed": safe,
        }

    def stopped_pool_payload(self, sync_status: str = "syncing", remaining_blocks: int = 5) -> dict:
        payload = {
            "overall": "syncing" if sync_status != "synced" else "ok",
            "sync_warnings": [] if sync_status == "synced" else ["behind"],
            "containers": {status_sampler.POOL_CONTAINER: {"running": False}},
            "sync_progress": {
                "status": sync_status,
                "remaining_blocks": remaining_blocks,
                "chain_block_count": 1000,
                "peer_count": 2,
            },
            "miner_health": {"connected_count": 0, "managed_count": 0},
            "pool": {"metrics": {"active_connections": 0}, "source_job_health": {}},
            "pool_metrics": {"active_connections": 0, "source_job_health": {}},
        }
        if sync_status == "synced":
            payload["sync_progress"]["nodes"] = {
                "blockdag-node-1": {
                    "canonical_mining_safety": self.canonical_safety(True),
                    "native_template_health": self.native_template_health(True),
                }
            }
        return payload

    def evm_gap_payload(self, *, lag: int = 14_100, local: int = 11_690_000) -> dict:
        reference = local + lag
        return {
            "overall": "syncing",
            "sync_warnings": ["local EVM is behind public reference"],
            "containers": {status_sampler.POOL_CONTAINER: {"running": False}},
            "sync_progress": {
                "status": "syncing",
                "source": "node:eth_syncing",
                "current_block_source": "eth_syncing",
                "current_block": local,
                "highest_block": reference,
                "remaining_blocks": lag,
                "evm_block_count": local,
                "evm_reference_block_count": reference,
                "evm_lag_to_reference": lag,
                "nodes": {},
            },
            "sync_health": {},
            "nodes": {},
            "miner_health": {"connected_count": 0, "managed_count": 0},
            "pool": {"metrics": {"active_connections": 0}, "source_job_health": {}},
            "pool_metrics": {"active_connections": 0, "source_job_health": {}},
        }

    def native_peer_lag_payload(self, *, height: int = 12_115_316, peer_lag: int = 1_200) -> dict:
        return {
            "overall": "syncing",
            "sync_warnings": ["native peers are ahead"],
            "containers": {status_sampler.POOL_CONTAINER: {"running": False}},
            "sync_progress": {
                "status": "syncing",
                "chain_block_count": height,
                "current_block": height,
                "peer_ahead_blocks": peer_lag,
                "remaining_blocks": peer_lag,
                "peer_count": 2,
                "p2p_connections": 2,
                "nodes": {
                    "node": {
                        "status": "syncing",
                        "current_block": height,
                        "peer_ahead_blocks": peer_lag,
                        "peer_count": 2,
                        "p2p_connections": 2,
                    }
                },
            },
            "sync_health": {},
            "nodes": {"node": {"latest_block": height, "peer_ahead_blocks": peer_lag}},
            "miner_health": {"connected_count": 0, "managed_count": 0},
            "pool": {"metrics": {"active_connections": 0}, "source_job_health": {}},
            "pool_metrics": {"active_connections": 0, "source_job_health": {}},
        }

    def test_evm_reference_gap_stall_requires_restore_when_gap_does_not_close(self) -> None:
        now = 1_779_200_000
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE = pathlib.Path(tmpdir) / "evm-gap-watch.json"
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "best_lag_blocks": 14_100,
                        "first_unimproved_epoch": now - 901,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                decision = status_sampler.chain_state_restore_decision(
                    self.evm_gap_payload(lag=14_140, local=11_691_000)
                )

        self.assertTrue(decision["should_repair"])
        self.assertFalse(decision["hard"])
        self.assertIn("EVM reference gap has not improved", decision["reasons"][0])
        self.assertTrue(decision["evm_reference_gap"]["restore_required"])

    def test_evm_reference_gap_stall_is_advisory_when_native_paid_mining_is_safe(self) -> None:
        now = 1_779_200_000
        payload = self.evm_gap_payload(lag=14_140, local=11_691_000)
        payload["sync_health"] = {"pool_has_recent_paid_work": True}
        payload["sync_progress"]["nodes"] = {
            "node": {"native_template_health": self.native_template_health(True)}
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE = pathlib.Path(tmpdir) / "evm-gap-watch.json"
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "best_lag_blocks": 14_100,
                        "first_unimproved_epoch": now - 901,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                decision = status_sampler.chain_state_restore_decision(payload)

        self.assertFalse(decision["should_repair"])
        self.assertFalse(decision["evm_reference_gap"]["restore_required"])
        self.assertTrue(decision["evm_reference_gap"]["would_restore_required"])
        self.assertTrue(decision["evm_reference_gap"]["restore_suppressed_by_native_paid_work"])
        self.assertIn("native mining safety", decision["evm_reference_gap"]["reason"])

    def test_evm_reference_gap_stall_is_advisory_when_native_chain_progress_is_safe_without_recent_paid_work(self) -> None:
        now = 1_779_200_000
        payload = self.evm_gap_payload(lag=14_140, local=11_691_000)
        payload["sync_health"] = {"native_chain_progress_safe": True}
        payload["sync_progress"]["nodes"] = {
            "node": {"native_template_health": self.native_template_health(True)}
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE = pathlib.Path(tmpdir) / "evm-gap-watch.json"
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "best_lag_blocks": 14_100,
                        "first_unimproved_epoch": now - 901,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                decision = status_sampler.chain_state_restore_decision(payload)

        self.assertFalse(decision["should_repair"])
        self.assertFalse(decision["evm_reference_gap"]["restore_required"])
        self.assertTrue(decision["evm_reference_gap"]["would_restore_required"])
        self.assertTrue(decision["evm_reference_gap"]["restore_suppressed_by_native_mining_safety"])
        self.assertIn("native mining safety", decision["evm_reference_gap"]["reason"])

    def test_evm_reference_gap_still_restores_when_native_template_proof_is_unsafe(self) -> None:
        now = 1_779_200_000
        payload = self.evm_gap_payload(lag=14_140, local=11_691_000)
        payload["sync_progress"]["nodes"] = {
            "node": {"native_template_health": self.native_template_health(False)}
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE = pathlib.Path(tmpdir) / "evm-gap-watch.json"
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "best_lag_blocks": 14_100,
                        "first_unimproved_epoch": now - 901,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                decision = status_sampler.chain_state_restore_decision(payload)

        self.assertTrue(decision["should_repair"])
        self.assertTrue(decision["evm_reference_gap"]["restore_required"])
        self.assertFalse(decision["evm_reference_gap"]["restore_suppressed_by_native_mining_safety"])

    def test_stalled_import_watch_resets_invalid_zero_epoch(self) -> None:
        now = 1_779_200_000
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.CHAIN_STATE_IMPORT_WATCH_FILE = pathlib.Path(tmpdir) / "import-watch.json"
            status_sampler.CHAIN_STATE_IMPORT_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "height": 12_115_316,
                        "lag_blocks": 1_260,
                        "first_stalled_epoch": 0,
                        "min_lag_blocks": 1_100,
                        "max_lag_blocks": 1_260,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                state = status_sampler.update_stalled_import_watch(
                    self.native_peer_lag_payload(height=12_115_316, peer_lag=1_260)
                )

        self.assertTrue(state["candidate"])
        self.assertTrue(state["native_p2p_lag_evidence"])
        self.assertEqual(now, state["first_stalled_epoch"])
        self.assertEqual(0, state["stalled_seconds"])
        self.assertFalse(state["restore_required"])
        self.assertIn("invalid previous stall epoch reset", state["reason"])

    def test_stalled_import_watch_ignores_public_gap_without_native_peer_evidence(self) -> None:
        now = 1_779_200_000
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.CHAIN_STATE_IMPORT_WATCH_FILE = pathlib.Path(tmpdir) / "import-watch.json"
            status_sampler.CHAIN_STATE_IMPORT_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "height": 11_691_000,
                        "lag_blocks": 14_140,
                        "first_stalled_epoch": now - 3600,
                        "min_lag_blocks": 14_000,
                        "max_lag_blocks": 14_140,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                state = status_sampler.update_stalled_import_watch(
                    self.evm_gap_payload(lag=14_140, local=11_691_000)
                )

        self.assertFalse(state["candidate"])
        self.assertFalse(state["native_p2p_lag_evidence"])
        self.assertEqual(0, state["first_stalled_epoch"])
        self.assertFalse(state["restore_required"])
        self.assertIn("no active native P2P peer-lag evidence", state["reason"])

    def test_cached_evm_restore_flag_is_not_hard_when_native_paid_mining_is_safe(self) -> None:
        payload = self.evm_gap_payload(lag=14_140, local=11_691_000)
        payload["sync_health"] = {
            "needs_chain_data_restore": True,
            "evm_reference_gap_stalled": True,
            "evm_reference_gap_watch": {"restore_required": True},
            "pool_has_recent_paid_work": True,
        }
        payload["sync_progress"]["nodes"] = {
            "node": {"native_template_health": self.native_template_health(True)}
        }

        self.assertEqual([], status_sampler.chain_state_restore_hard_reasons(payload))

    def test_cached_evm_restore_flag_is_not_hard_when_native_chain_progress_is_safe_without_paid_work(self) -> None:
        payload = self.evm_gap_payload(lag=14_140, local=11_691_000)
        payload["sync_health"] = {
            "needs_chain_data_restore": True,
            "evm_reference_gap_stalled": True,
            "evm_reference_gap_watch": {"restore_required": True},
            "native_chain_progress_safe": True,
        }
        payload["sync_progress"]["nodes"] = {
            "node": {"native_template_health": self.native_template_health(True)}
        }

        self.assertEqual([], status_sampler.chain_state_restore_hard_reasons(payload))

    def test_evm_reference_gap_watch_resets_when_gap_closes_enough(self) -> None:
        now = 1_779_200_000
        with tempfile.TemporaryDirectory() as tmpdir:
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE = pathlib.Path(tmpdir) / "evm-gap-watch.json"
            status_sampler.EVM_REFERENCE_GAP_WATCH_FILE.write_text(
                json.dumps(
                    {
                        "candidate": True,
                        "best_lag_blocks": 14_100,
                        "first_unimproved_epoch": now - 901,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(status_sampler.time, "time", return_value=now):
                decision = status_sampler.chain_state_restore_decision(
                    self.evm_gap_payload(lag=14_030, local=11_691_000)
                )

        self.assertFalse(decision["should_repair"])
        self.assertEqual(0, decision["evm_reference_gap"]["stalled_seconds"])
        self.assertEqual(14_030, decision["evm_reference_gap"]["best_lag_blocks"])

    def test_starts_stopped_pool_when_asic_lan_neighbor_is_present(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ASIC_LAN_CIDRS"] = "192.168.1.0/24"
        status_sampler.read_neighbor_macs = lambda: {"192.168.1.107": "28:e2:97:1e:c0:b5"}

        def fake_run(command: list[str], timeout: int = 20):
            commands.append(command)
            return self.command_result(command)

        status_sampler.run = fake_run

        repair = status_sampler.mining_imperative_repair(
            self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        )

        self.assertTrue(self.pool_compose_start_seen(commands))
        self.assertIn(f"started_container:{status_sampler.POOL_CONTAINER}", repair["actions"])

    def test_visible_asic_lan_neighbor_does_not_start_pool_while_syncing(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ASIC_LAN_CIDRS"] = "192.168.1.0/24"
        status_sampler.read_neighbor_macs = lambda: {"192.168.1.107": "28:e2:97:1e:c0:b5"}
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(
            self.stopped_pool_payload(sync_status="syncing", remaining_blocks=5)
        )

        self.assertFalse(self.pool_compose_start_seen(commands))
        self.assertNotIn(f"started_container:{status_sampler.POOL_CONTAINER}", repair["actions"])

    def test_synced_status_without_native_proof_does_not_start_pool(self) -> None:
        commands = []
        incidents = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["sync_progress"].pop("nodes", None)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        status_sampler.read_neighbor_macs = lambda: {}
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)
        status_sampler.append_incident = (
            lambda event_type, severity, *_args, **_kwargs: incidents.append((event_type, severity))
        )

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertFalse(self.pool_compose_start_seen(commands))
        self.assertNotIn(f"started_container:{status_sampler.POOL_CONTAINER}", repair["actions"])
        self.assertIn(("mining_imperative_pool_start_blocked", "warning"), incidents)

    def test_public_chain_divergence_leaves_running_pool_up(self) -> None:
        commands = []
        incidents = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["sync_health"] = {"public_chain_divergence": True}
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)
        status_sampler.append_incident = (
            lambda event_type, severity, *_args, **_kwargs: incidents.append((event_type, severity))
        )

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertFalse(any(command[-2:] == ["stop", status_sampler.POOL_CONTAINER] for command in commands))
        self.assertIn(f"left_container_running:{status_sampler.POOL_CONTAINER}:public_chain_divergence", repair["actions"])
        self.assertIn(("public_chain_divergence_left_pool_running", "warning"), incidents)
        self.assertFalse(any(command[:2] == ["docker", "start"] for command in commands))

    def test_chain_state_restore_leaves_running_pool_up_before_self_heal(self) -> None:
        commands = []
        incidents = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=500)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["sync_health"] = {
            "needs_chain_data_restore": True,
            "chain_data_restore_nodes": {"node": {"reasons": ["node DAG tip/block data is damaged"]}},
        }
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)
        status_sampler.append_incident = (
            lambda event_type, severity, *_args, **_kwargs: incidents.append((event_type, severity))
        )
        status_sampler.update_stalled_import_watch = lambda _payload: {}
        status_sampler.start_chain_state_self_heal = lambda _payload, _decision: True

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertFalse(any(command[-2:] == ["stop", status_sampler.POOL_CONTAINER] for command in commands))
        self.assertIn(f"left_container_running:{status_sampler.POOL_CONTAINER}:chain_state_restore", repair["actions"])
        self.assertIn("started_chain_state_self_heal", repair["actions"])
        self.assertIn(("chain_state_restore_left_pool_running", "warning"), incidents)

    def test_compose_command_uses_stable_project_name_for_symlinked_runtime(self) -> None:
        os.environ.pop("BDAG_COMPOSE_PROJECT_NAME", None)
        os.environ.pop("COMPOSE_PROJECT_NAME", None)
        os.environ["BDAG_PROJECT_ROOT"] = "/home/jeremy/blockdag-asic-pool"

        command = pool_ops.docker_compose_command("ps")

        self.assertIn("-p", command)
        self.assertEqual(command[command.index("-p") + 1], "blockdag-asic-pool")

    def test_leaves_stopped_idle_pool_when_chain_is_synced_without_miner_demand(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ASIC_LAN_CIDRS"] = "192.168.1.0/24"
        status_sampler.read_neighbor_macs = lambda: {}
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(self.stopped_pool_payload(sync_status="synced", remaining_blocks=0))

        self.assertFalse(self.pool_compose_start_seen(commands))
        self.assertNotIn(f"started_container:{status_sampler.POOL_CONTAINER}", repair["actions"])

    def test_does_not_start_pool_without_miner_demand_or_ready_chain(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ASIC_LAN_CIDRS"] = "192.168.1.0/24"
        status_sampler.read_neighbor_macs = lambda: {}
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(self.stopped_pool_payload(sync_status="syncing", remaining_blocks=12))

        self.assertFalse(self.pool_compose_start_seen(commands))
        self.assertEqual(repair["actions"], [])

    def test_catchup_policy_does_not_pause_on_syncing_when_mining_ready(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=5)
        payload["overall"] = "ok"
        payload["sync_warnings"] = []
        payload["can_mine"] = True
        payload["can_submit_blocks"] = True
        payload["catchup_policy"] = {"mining_ready": True}

        policy = status_sampler.catchup_policy_from_payload(payload)

        self.assertFalse(policy["active"])
        self.assertFalse(policy["syncing_active"])
        self.assertEqual(policy["trigger"], "")
        self.assertEqual(policy["lag_blocks"], 5)

    def test_catchup_policy_treats_remaining_blocks_as_advisory_when_paid_work_is_recent(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=14_982)
        payload["sync_health"] = {"pool_has_recent_paid_work": True}
        payload["catchup_policy"] = {
            "active": True,
            "syncing_active": True,
            "lag_blocks": 14_982,
            "threshold_blocks": 300,
        }
        payload["sync_progress"]["nodes"] = {
            "node": {"remaining_blocks": 14_982, "peer_ahead_blocks": 24}
        }

        policy = status_sampler.catchup_policy_from_payload(payload)

        self.assertFalse(policy["active"])
        self.assertFalse(policy["syncing_active"])
        self.assertTrue(policy["mining_ready"])
        self.assertTrue(policy["remaining_blocks_advisory"])
        self.assertEqual(policy["lag_blocks"], 24)
        self.assertEqual(policy["trigger"], "")

    def test_catchup_policy_treats_remaining_blocks_as_advisory_when_native_chain_progress_is_safe(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=14_982)
        payload["sync_health"] = {"native_chain_progress_safe": True}
        payload["catchup_policy"] = {
            "active": True,
            "syncing_active": True,
            "lag_blocks": 14_982,
            "threshold_blocks": 300,
        }
        payload["sync_progress"]["nodes"] = {
            "node": {
                "remaining_blocks": 14_982,
                "peer_ahead_blocks": 4,
                "native_template_health": self.native_template_health(True),
            }
        }

        policy = status_sampler.catchup_policy_from_payload(payload)

        self.assertFalse(policy["active"])
        self.assertFalse(policy["syncing_active"])
        self.assertTrue(policy["mining_ready"])
        self.assertTrue(policy["remaining_blocks_advisory"])
        self.assertTrue(policy["native_advisory_safe"])
        self.assertEqual(policy["lag_blocks"], 4)
        self.assertEqual(policy["trigger"], "")

    def test_catchup_policy_keeps_pause_when_native_template_proof_is_unsafe(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=14_982)
        payload["catchup_policy"] = {
            "active": True,
            "syncing_active": True,
            "lag_blocks": 14_982,
            "threshold_blocks": 300,
        }
        payload["sync_progress"]["nodes"] = {
            "node": {
                "remaining_blocks": 14_982,
                "peer_ahead_blocks": 14_982,
                "native_template_health": self.native_template_health(False),
            }
        }

        policy = status_sampler.catchup_policy_from_payload(payload)

        self.assertTrue(policy["active"])
        self.assertTrue(policy["syncing_active"])
        self.assertFalse(policy["native_advisory_safe"])
        self.assertFalse(policy["remaining_blocks_advisory"])
        self.assertEqual(policy["trigger"], "node_syncing")

    def test_apply_catchup_node_runtime_skips_recent_paid_work(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=14_982)
        payload["sync_health"] = {"pool_has_recent_paid_work": True}
        status_sampler.set_runtime_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runtime env must not be changed while paid work is recent")
        )
        status_sampler.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("node must not be recreated while paid work is recent")
        )

        applied = status_sampler.apply_catchup_node_runtime(
            payload,
            {"active": True, "lag_blocks": 14_982, "threshold_blocks": 300},
        )

        self.assertFalse(applied)

    def test_apply_catchup_node_runtime_skips_native_safe_evm_advisory_sync(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=14_982)
        payload["sync_health"] = {"native_chain_progress_safe": True}
        payload["sync_progress"]["nodes"] = {
            "node": {
                "remaining_blocks": 14_982,
                "peer_ahead_blocks": 4,
                "native_template_health": self.native_template_health(True),
            }
        }
        status_sampler.set_runtime_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runtime env must not be changed when native mining safety is proven")
        )
        status_sampler.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("node must not be recreated when native mining safety is proven")
        )

        applied = status_sampler.apply_catchup_node_runtime(
            payload,
            status_sampler.catchup_policy_from_payload(payload),
        )

        self.assertFalse(applied)

    def test_apply_catchup_node_runtime_skips_stale_paid_work_evidence(self) -> None:
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=14_982)
        payload["sync_health"] = {
            "pool_paid_work_state": {
                "accepted_block_recent": False,
                "accepted_block_submissions": 2061,
                "last_accepted_age_seconds": 69.978,
            }
        }
        status_sampler.set_runtime_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runtime env must not be changed while accepted block history exists")
        )
        status_sampler.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("node must not be recreated while accepted block history exists")
        )

        applied = status_sampler.apply_catchup_node_runtime(
            payload,
            {"active": True, "lag_blocks": 14_982, "threshold_blocks": 300},
        )

        self.assertFalse(applied)

    def test_recreate_node_services_blocks_running_pool(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        ok, results = status_sampler.recreate_node_services(payload, "unit test blocked recreate")

        self.assertFalse(ok)
        self.assertEqual(results[0]["service"], "node")
        self.assertTrue(results[0]["blocked"])
        self.assertIn("paid-block evidence", results[0]["blocked_reason"])
        self.assertEqual(commands, [])

    def test_syncing_node_leaves_running_pool_up_below_lag_threshold(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ENABLE_NODE_MINING"] = "1"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag,miner"
        os.environ["BDAG_NODE_MINING_ARGS"] = (
            "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc "
            "--obsoleteheight=20"
        )
        os.environ["NODE_ARGS_APPEND"] = os.environ["BDAG_NODE_MINING_ARGS"]
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=5)
        payload["overall"] = "ok"
        payload["sync_warnings"] = []
        payload["can_mine"] = True
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        with tempfile.TemporaryDirectory() as tmp:
            status_sampler.PROJECT_ROOT = pathlib.Path(tmp)
            repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn(f"template_pause:{status_sampler.POOL_CONTAINER}:catchup_pause", repair["actions"])
        self.assertNotIn(f"stopped_container:{status_sampler.POOL_CONTAINER}:catchup_pause", repair["actions"])
        self.assertNotIn("applied_catchup_node_runtime", repair["actions"])
        self.assertNotIn("BDAG_ENABLE_NODE_MINING", env_updates)
        self.assertFalse(any(command[-2:] == ["stop", status_sampler.POOL_CONTAINER] for command in commands))

    def test_catchup_pause_leaves_pool_running_without_node_runtime_mutation(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ENABLE_NODE_MINING"] = "1"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag,miner"
        os.environ["BDAG_NODE_MINING_ARGS"] = (
            "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc "
            "--obsoleteheight=20"
        )
        os.environ["NODE_ARGS_APPEND"] = os.environ["BDAG_NODE_MINING_ARGS"]
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=450)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        payload["catchup_policy"] = {
            "active": True,
            "lag_blocks": 450,
            "threshold_blocks": 300,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            status_sampler.PROJECT_ROOT = root
            (root / "node.conf").write_text(
                "\n".join(
                    [
                        "cache=2048",
                        "cache.database=70",
                        "miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc",
                        "modules=Blockdag",
                        "modules=miner",
                        "miner=true",
                        'evmenv="--metrics --cache 2048"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_set_runtime_env(key: str, value: str):
                env_updates[key] = value
                os.environ[key] = value
                return [f"/runtime/{key}"]

            def fake_run(command: list[str], timeout: int = 20):
                commands.append(command)
                return self.command_result(command)

            status_sampler.set_runtime_env_value = fake_set_runtime_env
            status_sampler.detect_total_memory_bytes = lambda: 16 * 1024 * 1024 * 1024
            status_sampler.run = fake_run

            repair = status_sampler.mining_imperative_repair(payload)
            node_conf = (root / "node.conf").read_text(encoding="utf-8")

        self.assertIn(f"template_pause:{status_sampler.POOL_CONTAINER}:catchup_pause", repair["actions"])
        self.assertNotIn(f"stopped_container:{status_sampler.POOL_CONTAINER}:catchup_pause", repair["actions"])
        self.assertNotIn("applied_catchup_node_runtime", repair["actions"])
        self.assertEqual(env_updates, {})
        self.assertIn("cache=2048", node_conf)
        self.assertIn("--cache 2048", node_conf)
        self.assertIn("miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc", node_conf)
        self.assertIn("miner=true", node_conf)
        self.assertFalse(any(command[-2:] == ["stop", status_sampler.POOL_CONTAINER] for command in commands))
        self.assertFalse(any("--force-recreate" in command for command in commands))

    def test_catchup_pause_does_not_restart_stopped_pool_for_visible_miners(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        os.environ["NODE_ARGS_APPEND"] = ""
        payload = self.stopped_pool_payload(sync_status="syncing", remaining_blocks=450)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        payload["catchup_policy"] = {
            "active": True,
            "lag_blocks": 450,
            "threshold_blocks": 300,
        }

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        with tempfile.TemporaryDirectory() as tmp:
            status_sampler.PROJECT_ROOT = pathlib.Path(tmp)
            repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn(f"started_container:{status_sampler.POOL_CONTAINER}", repair["actions"])
        self.assertNotIn(f"stopped_container:{status_sampler.POOL_CONTAINER}:catchup_pause", repair["actions"])
        self.assertFalse(any(command[:2] == ["docker", "start"] for command in commands))

    def test_reenables_guard_timer_when_it_drifts_disabled(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = ["bdag-stack-sentinel.timer"]

        def fake_run(command: list[str], timeout: int = 20):
            commands.append(command)
            if command[:3] == ["systemctl", "--user", "is-enabled"]:
                return self.command_result(command, 1, "disabled\n", "")
            if command[:3] == ["systemctl", "--user", "is-active"]:
                return self.command_result(command, 3, "inactive\n", "")
            return self.command_result(command)

        status_sampler.run = fake_run
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn(["systemctl", "--user", "enable", "--now", "bdag-stack-sentinel.timer"], commands)
        self.assertIn("repaired_unit:bdag-stack-sentinel.timer", repair["actions"])

    def test_repairs_missing_tracked_miners_from_pool_activity(self) -> None:
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 0, "connected_count": 1, "managed_count": 0}
        activity = {"miners": [{"ip": "172.18.0.1"}], "unattributed_valid_shares": 8, "unattributed_blocks": 1}
        status_sampler.collect_pool_activity = lambda lines=0: activity
        status_sampler.upsert_pool_activity_miners = lambda _activity: {
            "miners": [{"ip": "192.168.1.107", "mac": "28:e2:97:1e:c0:b5"}]
        }
        status_sampler.read_miner_registry = lambda: {"miners": []}

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn("repaired_tracked_miners", repair["actions"])

    def test_no_logs_pool_metrics_miner_demand_is_not_a_tracking_gap(self) -> None:
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["pool"]["metrics"]["active_connections"] = 4
        payload["pool_metrics"]["active_connections"] = 4
        payload["pool"]["source_job_health"] = {"authorized_miners": 4, "ready_miners": 4}
        payload["miner_health"] = {
            "failures": [],
            "warnings": [],
            "miners": [],
            "connected_count_effective": 4,
            "connected_count_source": "pool-metrics",
        }
        status_sampler.collect_pool_activity = lambda lines=0: (_ for _ in ()).throw(
            AssertionError("pool-metrics fallback must not trigger tracked-miner repair")
        )

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn("repaired_tracked_miners", repair["actions"])

    def test_detects_miner_activity_visibility_gap_after_power_cycle(self) -> None:
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {
            "tracked_count": 4,
            "connected_count": 4,
            "managed_count": 4,
            "miners": [
                {
                    "mac": "28:e2:97:4d:44:3a",
                    "device_type": "asic",
                    "managed": True,
                    "connected": True,
                    "shares": 0,
                    "share_work": 0,
                    "last_share_epoch": 1000,
                    "last_share_age_seconds": 12,
                }
            ],
        }
        payload["pool_health"] = {"valid_share_count": 8, "last_valid_share_age_seconds": 10}

        self.assertTrue(status_sampler.status_payload_has_miner_activity_visibility_gap(payload))

    def test_visible_miner_shares_do_not_trigger_activity_visibility_repair(self) -> None:
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {
            "tracked_count": 4,
            "connected_count": 4,
            "managed_count": 4,
            "miners": [
                {
                    "mac": "28:e2:97:4d:44:3a",
                    "device_type": "asic",
                    "managed": True,
                    "connected": True,
                    "shares": 3,
                    "share_work": 99,
                }
            ],
        }
        payload["pool_health"] = {"valid_share_count": 8, "last_valid_share_age_seconds": 10}

        self.assertFalse(status_sampler.status_payload_has_miner_activity_visibility_gap(payload))

    def test_repairs_miner_activity_visibility_from_deep_pool_activity(self) -> None:
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {
            "tracked_count": 4,
            "connected_count": 4,
            "managed_count": 4,
            "miners": [
                {
                    "mac": "28:e2:97:4d:44:3a",
                    "device_type": "asic",
                    "managed": True,
                    "connected": True,
                    "shares": 0,
                    "share_work": 0,
                }
            ],
        }
        payload["pool_health"] = {"valid_share_count": 8, "last_valid_share_age_seconds": 10}
        activity_calls = []
        activity = {
            "miners": [{"ip": "192.168.1.102", "shares": 5, "share_work": 12345}],
            "unattributed_valid_shares": 0,
            "unattributed_blocks": 0,
        }
        status_sampler.collect_pool_activity = lambda lines=0: activity_calls.append(lines) or activity
        status_sampler.upsert_pool_activity_miners = lambda _activity: {
            "miners": [
                {
                    "ip": "192.168.1.102",
                    "mac": "28:e2:97:4d:44:3a",
                    "last_pool_seen_epoch": 1_000_000,
                    "last_share_epoch": 1_000_000,
                    "last_shares_window": 5,
                    "last_share_work_window": 12345,
                }
            ]
        }
        old_time = status_sampler.time.time
        status_sampler.time.time = lambda: 1_000_010
        self.addCleanup(lambda: setattr(status_sampler.time, "time", old_time))

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn(status_sampler.POOL_ACTIVITY_BOOTSTRAP_LOG_LINES, activity_calls)
        self.assertIn("repaired_miner_activity_visibility", repair["actions"])

    def test_enables_node_mining_template_support_when_miner_is_present(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        status_sampler.MINING_IMPERATIVE_START_POOL_ENABLED = False
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        def fake_run(command: list[str], timeout: int = 20):
            commands.append(command)
            return self.command_result(command)

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = fake_run

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn("enabled_node_mining_template_support", repair["actions"])
        self.assertEqual(env_updates["BDAG_ENABLE_NODE_MINING"], "1")
        self.assertEqual(env_updates["BDAG_NODE_MODULES"], "Blockdag,miner")
        self.assertIn("--miner", env_updates["NODE_ARGS_APPEND"])
        self.assertIn("--miner", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertIn("--miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertIn("--obsoleteheight=20", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--miningnopendingtx", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--allowminingwhennearlysynced", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--allowsubmitwhennotsynced", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertEqual(env_updates["NODE_ARGS_APPEND"], env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertTrue(any("--force-recreate" in command for command in commands))

    def test_node_mining_template_support_requires_native_proof(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["sync_progress"].pop("nodes", None)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        status_sampler.set_runtime_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("config edit must not run without native proof")
        )
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn("enabled_node_mining_template_support", repair["actions"])
        self.assertFalse(any("--force-recreate" in command for command in commands))

    def test_recent_paid_work_defers_node_mining_template_repair(self) -> None:
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        os.environ["NODE_ARGS_APPEND"] = ""
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        payload["sync_health"] = {"pool_has_recent_paid_work": True}
        status_sampler.set_runtime_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fresh paid block submissions should defer node config repair")
        )

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn("enabled_node_mining_template_support", repair["actions"])

    def test_stale_paid_work_evidence_blocks_live_node_mining_template_recreate(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        os.environ["NODE_ARGS_APPEND"] = ""
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        payload["sync_health"] = {
            "pool_paid_work_state": {
                "accepted_block_recent": False,
                "accepted_block_submissions": 2061,
                "last_accepted_age_seconds": 69.978,
            }
        }
        status_sampler.set_runtime_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stale-but-present accepted block evidence must block live node config repair")
        )
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn("enabled_node_mining_template_support", repair["actions"])
        self.assertFalse(any("--force-recreate" in command for command in commands))

    def test_node_mining_template_repair_preserves_node_conf_miner_module(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = ""
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            status_sampler.PROJECT_ROOT = root
            (root / "node.conf").write_text(
                "miningaddr=\n# modules=miner\n# miner=true\n",
                encoding="utf-8",
            )
            status_sampler.set_runtime_env_value = fake_set_runtime_env
            status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

            repair = status_sampler.mining_imperative_repair(payload)
            node_conf = (root / "node.conf").read_text(encoding="utf-8")

        self.assertIn("enabled_node_mining_template_support", repair["actions"])
        self.assertIn("miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc", node_conf)
        self.assertIn("modules=miner", node_conf)
        self.assertNotIn("\nminer=true", node_conf)

    def test_node_args_parser_accepts_nodeworker_embedded_node_args(self) -> None:
        address = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        command_line = f"nodeworker --node-args=--miner --miningaddr={address} --obsoleteheight=20"

        self.assertTrue(status_sampler.node_mining_args_are_safe_and_complete(command_line, address))

    def test_repairs_node_mining_args_when_unsafe_sync_bypass_is_present(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "1"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = (
            "--allowminingwhennearlysynced --allowsubmitwhennotsynced --miner "
            "--miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        )
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn("enabled_node_mining_template_support", repair["actions"])
        self.assertIn("--miner", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertIn("--obsoleteheight=20", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--miningnopendingtx", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--allowminingwhennearlysynced", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--allowsubmitwhennotsynced", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertEqual(env_updates["NODE_ARGS_APPEND"], env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertTrue(any("--force-recreate" in command for command in commands))

    def test_keeps_configured_miner_rpc_module(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        status_sampler.MINING_IMPERATIVE_START_POOL_ENABLED = False
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "1"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag,miner"
        os.environ["BDAG_NODE_MINING_ARGS"] = (
            "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc "
            "--obsoleteheight=20"
        )
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertEqual(repair["actions"], [])
        self.assertEqual(env_updates, {})
        self.assertFalse(any("--force-recreate" in command for command in commands))

    def test_recreates_node_when_live_process_has_unsafe_sync_bypass(self) -> None:
        commands = []
        env_updates = {}
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "1"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["BDAG_NODE_MINING_ARGS"] = (
            "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc "
            "--obsoleteheight=20"
        )
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        def fake_run(command: list[str], timeout: int = 20):
            commands.append(command)
            if "exec" in command and "-T" in command and any("ps -eo args" in part for part in command):
                stdout = (
                    "nodeworker --node-args=--allowminingwhennearlysynced --allowsubmitwhennotsynced --miner "
                    "--miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc\n"
                )
                return self.command_result(command, stdout=stdout)
            return self.command_result(command)

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = fake_run

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn("enabled_node_mining_template_support", repair["actions"])
        self.assertIn("--miner", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertIn("--obsoleteheight=20", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--miningnopendingtx", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--allowminingwhennearlysynced", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertNotIn("--allowsubmitwhennotsynced", env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertEqual(env_updates["NODE_ARGS_APPEND"], env_updates["BDAG_NODE_MINING_ARGS"])
        self.assertTrue(any("--force-recreate" in command for command in commands))

    def test_does_not_enable_node_mining_without_valid_address(self) -> None:
        commands = []
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["MINING_ADDRESS"] = "0x0000000000000000000000000000000000000000"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "0"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["containers"][status_sampler.POOL_CONTAINER]["running"] = True
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        status_sampler.run = lambda command, timeout=20: commands.append(command) or self.command_result(command)

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertNotIn("enabled_node_mining_template_support", repair["actions"])
        self.assertFalse(any("--force-recreate" in command for command in commands))

    def test_quarantines_fastsync_peer_returning_only_orphan_blocks(self) -> None:
        commands = []
        env_updates = {}
        peer_id = "16Uiu2HAkvvmkRJXJAZAWq3bFDzBAFQwQJ88PQqMedULsrv4t3XCD"
        status_sampler.MINING_IMPERATIVE_GUARD_UNITS = []
        os.environ["BDAG_DETECTED_NETWORK_TOPOLOGY"] = "asic-router"
        os.environ["BDAG_STORAGE_PROFILE"] = "usb-chain-internal-runtime"
        os.environ["BDAG_ENABLE_NODE_MINING"] = "1"
        os.environ["BDAG_NODE_MODULES"] = "Blockdag"
        os.environ["MINING_ADDRESS"] = "0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
        os.environ["BDAG_NODE_MINING_ARGS"] = (
            "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc "
            "--obsoleteheight=20 --maxinbound=1"
        )
        os.environ["BDAG_NODE_PEER_ADDRESSES"] = f"/ip4/10.0.0.2/tcp/8151/p2p/{peer_id},/ip4/3.3.3.3/tcp/8150/p2p/good"
        os.environ["BDAG_FASTSYNC_PEERS"] = f"/ip4/10.0.0.2/tcp/8151/p2p/{peer_id}"
        os.environ["BOOTSTRAP_PEER_ADDRESSES"] = f"/ip4/10.0.0.2/tcp/8151/p2p/{peer_id},/ip4/4.4.4.4/tcp/8150/p2p/good"
        os.environ["BDAG_NODE_SERVICES"] = "node"
        payload = self.stopped_pool_payload(sync_status="synced", remaining_blocks=0)
        payload["miner_health"] = {"tracked_count": 1, "connected_count": 1, "managed_count": 1}
        payload["nodes"] = {
            "node": {
                "tail": [
                    "Fast-sync range returned only orphan blocks; falling back to legacy sync DAG "
                    f"module=SYNC peer={peer_id} processID=54"
                ]
            }
        }

        def fake_set_runtime_env(key: str, value: str):
            env_updates[key] = value
            os.environ[key] = value
            return [f"/runtime/{key}"]

        def fake_run(command: list[str], timeout: int = 20):
            commands.append(command)
            return self.command_result(command)

        status_sampler.set_runtime_env_value = fake_set_runtime_env
        status_sampler.run = fake_run

        repair = status_sampler.mining_imperative_repair(payload)

        self.assertIn("quarantined_fastsync_orphan_peer", repair["actions"])
        self.assertNotIn(peer_id, env_updates["BDAG_NODE_PEER_ADDRESSES"])
        self.assertNotIn(peer_id, env_updates["BDAG_FASTSYNC_PEERS"])
        self.assertNotIn(peer_id, env_updates["BOOTSTRAP_PEER_ADDRESSES"])
        self.assertTrue(any("--force-recreate" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
